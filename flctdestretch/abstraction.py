import enum
import os
import time
from typing import Callable, TypedDict, Any

import numpy as np
from astropy.io import fits

from algorithm import (
    doreg, destr_control_points, reg_loop,
    DestretchLoopResult, DestretchParams
)
import processing
from utility import IndexSchema, load_image_data
from reference_method import RefMethod, OMargin, PreviousRef, MarginEndBehavior

class IterProcessArgs(TypedDict):
    """
    All available keyword arguments for relevant functions

    Attributes
    ----------
    kernel_sizes : list[int]
        the destretch kernel size, the size of each subframe to be processed
    index_schema : reference_method.IndexSchema
        the index schema to use for the input data files
    ref_method : reference_method.RefMethod
        the method to use to apply the reference image for destretching, if not
        specified, will use reference_method.OMargin in most cases
    """
    kernel_sizes: list[int]
    index_schema: IndexSchema
    ref_method: RefMethod
    out_paths: list[os.PathLike]

def fits_file_iter(
        in_filepaths: list[os.PathLike],
        iter_func: Callable[[np.ndarray], None],
        z_index: int | None = 0,
        ** kwargs
    ) -> None:
    """
    iterates over each data from each specified file calling the specified 
    iter_func and passing the fits file data to that funciton

    Parameters
    ----------
    in_filepaths:
        the list of file paths to process
    iter_func:
        the function that is called for each frame after the image data has 
        been processed it
    z_index:
        th z index slice to use in the image data if it is 3d data file (after 
        converted from index schema). Set to None if you want the image data to 
        remain as 3d
    """
    # iterate through each file data 
    print("Searching for image data in specified files...")
    for i in range(len(in_filepaths)):
        path = in_filepaths[i]
        image_data = load_image_data(path, z_index=z_index)
        iter_func(image_data)

def fits_file_destretch_iter(
        in_filepaths: list[os.PathLike],
        iter_func: Callable[[DestretchLoopResult], None],
        ** kwargs: IterProcessArgs
    ) -> None:
    """
    iterates over each data from each specified file and applies destretching
    to each of them, calling the specified iter_func and passing the result of
    destretching to that funciton

    Parameters
    ----------
    in_filepaths:
        the list of file paths to process
    iter_func:
        the function that is called for each frame after the image data has 
        been processed it
    """

    # get required kwargs or default values if not specified
    kernel_sizes: list[int] = kwargs.get("kernel_sizes", [64, 32])
    ref_method: RefMethod = kwargs.get("ref_method", OMargin(in_filepaths))

    # used to enforce the same resolution for all data files
    image_resolution = [-1,-1]

    # reference image to feed into next destretch loop
    reference_image: np.ndarray | None = None

    # iterate through each file
    print("Searching for image data in specified files...")
    for i in range(len(in_filepaths)):
        path = in_filepaths[i]
        
        # pass data to reference method so it can do its thing
        match ref_method:
            case OMargin():
                ref_method.pass_params(i)
        
        # get the image data from ref method if available otherwise load it
        image_data: np.ndarray = ref_method.get_original_data(i)
        if image_data is None:
            image_data = load_image_data(path)

        # ensure all data matches the first file's resolution
        if image_resolution[-1] < 0:
            image_resolution = (
                image_data.shape[-1], 
                image_data.shape[-2]
            )
        elif (
            image_resolution[-1] != image_data.shape[-1] or 
            image_resolution[-2] != image_data.shape[-2]
        ): 
            print(image_resolution, image_data.shape)
            raise Exception(f"Resolution mismatch for '{os.fspath(path)}'")

        # debug log
        # print(f"found {hdu_index} in {path}: {image_data.shape}")

        # get the reference image from the specified reference method
        reference_image = ref_method.get_reference(i)

        print(f"ref image checksum: {reference_image.sum()}")

        # perform image destretching
        print(f"processing image #{i}.." + in_filepaths[i])
        result = reg_loop(
            image_data,
            reference_image,
            kernel_sizes,
        )

        # ???? why does it change after the first time? why is the change 
        # different than just ref -= ref.mean()? 
        print(f"ref image checksum: {reference_image.sum()}")

        # call the function specified by caller
        iter_func(result)

def fits_file_process_iter(
        in_data_files: list[os.PathLike],
        in_off_files: list[os.PathLike],
        in_avg_files: list[os.PathLike],
        iter_func: Callable[[DestretchLoopResult], None],
        ** kwargs: IterProcessArgs
    ) -> None:
    """
    iterates over each data from each specified file and applies destretching
    to each of them, calling the specified iter_func and passing the result of
    destretching to that funciton

    Parameters
    ----------
    in_data_files:
        the list of file paths to process
    iter_func:
        the function that is called for each frame after the image data has 
        been processed it
    """

    # get required kwargs or default values if not specified
    kernel_sizes: list[int] = kwargs.get("kernel_sizes", [64, 32])
    index_schema: IndexSchema = kwargs.get("index_schema", IndexSchema.XYT)

    # ensure there is an offset for each data
    if(len(in_data_files) != len(in_off_files)):
        raise Exception("Each data file must have a corresponging offset")

    # used to enforce the same resolution for all data files
    image_resolution = [-1,-1]

    # iterate through each file
    print("Searching for image data in specified files...")
    for i in range(len(in_data_files)):
        path_data = in_data_files[i]
        path_off = in_off_files[i]
        path_avg = in_avg_files[i]
        
        # get the image data from ref method if available otherwise load it
        image_data = load_image_data(path_data)
        off_data = load_image_data(path_off, z_index=None)
        avg_data = load_image_data(path_avg, z_index=None)

        # ensure all data matches the first file's resolution
        if image_resolution[-1] < 0:
            image_resolution[-1] = image_data.shape[-1]
            image_resolution[-2] = image_data.shape[-2]
            
        elif (
            image_resolution[-1] != image_data.shape[-1] or 
            image_resolution[-2] != image_data.shape[-2] or
            image_resolution[-1] != off_data.shape[-1] or
            image_resolution[-2] != off_data.shape[-2] or
            image_resolution[-1] != avg_data.shape[-1] or
            image_resolution[-2] != avg_data.shape[-2] 
        ): 
            print(
                image_resolution, 
                image_data.shape, 
                off_data.shape, 
                avg_data.shape
            )
            raise Exception(
                f"Resolution mismatch for '{os.fspath(path_data), path_avg}'"
            )


        # # perform image destretching
        # print(f"processing image #{i}.." + in_data_files[i])
        # result = reg_loop(
        #     image_data,
        #     reference_image,
        #     kernel_sizes,
        #     mf=0.08,
        #     use_fft=True
        # )

        image_data -= image_data.mean()
        destr_params, rdisp = destr_control_points(
            image_data,
            np.zeros((1,1)), # kernel?
            border_offset=0, # should be default?
            spacing_ratio=0 # should be defailt?
        )

        # calculate the corrected result
        corrected_off_data = avg_data - off_data # this result should be disp - rdisp
        # swap the indices back around because we fucked up the order when 
        # writing the files
        # apod_window = processing.apod_mask(
        #     destr_params.kx, 
        #     destr_params.ky, 
        #     destr_params.mf
        # )
        # subfield_fftconj, _ = doref(
        #     ref, # why do we need reference here? (we shouldn't)
        #     apod_window, 
        #     destr_params
        # )
        # # fft
        # disp = controlpoint_offsets_fft(
        #     image_data, 
        #     subfield_fftconj, # problematic
        #     apod_window, 
        #     processing.smouth(destr_params.kx, destr_params.ky), 
        #     destr_params
        # )
        result = (
            doreg(
                image_data, 
                rdisp,
                rdisp - corrected_off_data * 2,
                destr_params
            ),
            None,
            None,
            destr_params,
        )

        # call the function specified by caller
        iter_func(result)

def destretch_files(
        in_data_files: list[os.PathLike],
        in_off_files: list[os.PathLike],
        in_avg_files: list[os.PathLike],
        out_dir: os.PathLike,
        out_filename: str = "destretched",
        ** kwargs: IterProcessArgs
    ) -> None:
    """
    Compute the destretched result of data from all given files, and export to 
    new files

    Parameters
    ----------
    filepaths : list[str]
        list of files in order to treat as image sequence for destretching
    kernel_sizes : ndarray (kx, ky, 2)
        the destretch kernel size, the size of each subframe to be processed
    index_schema : reference_method.IndexSchema
        the index schema to use for the input data files
    ref_method : reference_method.RefMethod
        the method to use to apply the reference image for destretching, if not
        specified, will use reference_method.OMargin
    ** kwargs: 
        see IterProcessArgs class for all available arguments
    """

    # start timing 
    time_begin = time.time()

    # number of digits needed to accurately order the output files
    out_name_digits: int = len(str(len(in_data_files)))
    index: int = 0

    # to store output paths
    out_paths: list[os.PathLike] | None = kwargs.get("out_paths", None)

    # ensure output directory exists
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # function to handle processing of destretch loop results for each image
    # frame found in data files
    def iter_process(result: DestretchLoopResult):
        nonlocal index

        # output the result as a new fits file
        out_num = f"{index:0{out_name_digits}}"
        out_path = os.path.join(out_dir, out_filename + f"{out_num}.fits")
        fits.writeto(out_path, result[0], overwrite=True)
        print(f"destretched {out_path}")
        if out_paths is not None: out_paths.append(out_path)
        index += 1

    # iterate through file datas and call iter_process on destretched results
    fits_file_process_iter(
        in_data_files, in_off_files, in_avg_files, 
        iter_process, 
        ** kwargs
    )

    # calculate time in appropriate units
    time_end = time.time()
    time_taken = time_end - time_begin
    time_units = "seconds"
    if time_taken >= 120:
        time_taken /= 60
        time_units = "minutes"
        if time_taken >= 120:
            time_taken /= 60
            time_units = "hours"
    
    # output time elapsed
    print(
        "Destretching complete! Time elapsed: " +
        f"{time_taken:.3f} {time_units}"
    )

def calc_offset_vectors(
        in_filepaths: list[os.PathLike],
        out_dir: os.PathLike,
        out_filename: str = "offsets",
        ** kwargs: IterProcessArgs
    ) -> None:
    """
    calcuates the offset vectors from destretching and outputs each of them as 
    .fits files

    Parameters
    ----------
    in_filepaths:
        the list of fits filepaths to process data from
    out_dir:
        the directory where the offset vector files will be stored
    out_filename:
        the base name of each file (numbers will be appended to the end of them)
    ** kwargs: 
        see IterProcessArgs class for all available arguments
    """

    # number of digits needed to accurately order the output files
    out_name_digits: int = len(str(len(in_filepaths)))
    index: int = 0

    # to store output paths
    out_paths: list[os.PathLike] | None = kwargs.get("out_paths", None)

    # ensure output directory exists
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # define the processing to calculate and store the offset files
    def process_iter(result: DestretchLoopResult):
        nonlocal index

        # use final displacement sum 'disp_sum' - 'rdisp_sum'
        _, disp_sum, rdisp_sum, _ = result
        offsets = disp_sum - rdisp_sum

        # output the vectors as a new fits file
        out_num = f"{index:0{out_name_digits}}"
        out_path = os.path.join(out_dir, out_filename + f"{out_num}.off.fits")
        fits.writeto(out_path, offsets, overwrite=True)
        if out_paths is not None: out_paths.append(out_path)
        index += 1
    
    # use default previousRef method if not specified
    kwargs["ref_method"] = kwargs.get("ref_method", PreviousRef(in_filepaths))

    # iterate over data in files
    fits_file_destretch_iter(in_filepaths, process_iter, ** kwargs)

def calc_rolling_mean(
        in_filepaths: list[os.PathLike],
        out_dir: os.PathLike,
        out_filename: str = "offsets",
        margin_left: int = 5,
        margin_right: int = 5,
        end_behavior: MarginEndBehavior = MarginEndBehavior.KEEP_RANGE,
        ** kwargs: IterProcessArgs
    )-> None:
    """
    TODO this function needs to be revised, writing files at either end of 
    margin seems to not work properly

    calculate a rolling mean for the given input filepaths (which should be 
    files generated by the calc_offset_vectors or similar function), and output
    a corresponding mean matrix with the specified range, as a fits file in the 
    specified output directory

    Paramaters
    ----------
    in_filepaths:
        the list of fits filepaths to process data from
    out_dir:
        the directory where the offset vector files will be stored
    out_filename:
        the base name of each file (numbers will be appended to the end of them)
    margin_left:
        number of images before current image to include in ref margin
    margin_right:
        number of images after current image to include in ref margin
    end_behavior:
        how the function decides what data to use for the margin when it 
        collides with an edge of the data list
    ** kwargs: 
        see IterProcessArgs class for all available arguments
    """

    # ensure output directory exists
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    
    # to store output paths
    out_paths: list[os.PathLike] | None = kwargs.get("out_paths", None)

    # data structures to store info about original datas
    file_count = len(in_filepaths)
    original_data: list[np.ndarray] = []
    avg_data: list[np.ndarray] = []
    original_data_off: int = 0

    # number of digits needed to accurately order the output files
    out_name_digits: int = len(str(file_count))
    index: int = 0
    index_avged: int = 0
    index_written: int = 0

    # track the data average from the previous iterations
    data_avg: np.ndarray | None = None
    data_avg_start: int = 0
    data_avg_end: int = 0
    data_avg_range: int = 0

    # define the local function that iterates over each data frame
    def iter_data(data: np.ndarray):
        nonlocal data_avg, data_avg_start, data_avg_end, data_avg_range
        nonlocal index, index_written, index_avged, original_data_off

        print(f"averaging data #{index}..")

        # calculate the local margin values
        margin_min = index_avged - margin_left
        margin_max = index_avged + margin_right + 1
        if margin_min < 0 or margin_max > file_count:
            match end_behavior:
                case MarginEndBehavior.KEEP_RANGE:
                    margin_range = margin_max - margin_min
                    if file_count < margin_range:
                        margin_min = 0
                        margin_max = file_count
                    elif margin_min < 0:
                        margin_min = 0
                        margin_max = margin_range
                    elif margin_max > file_count:
                        margin_max = file_count
                        margin_min = file_count - margin_range
                case MarginEndBehavior.TRIM_MARGINS:
                    margin_min = max(0, margin_min)
                    margin_max = min(file_count, margin_max)
        margin_range: int = margin_max - margin_min
        
        # append current data to data list
        local_index = index - original_data_off
        if local_index >= len(original_data):
            original_data.append(data)
        
        # if the entire margin is within the data list
        local_marg_max = margin_max - original_data_off
        if local_marg_max <= len(original_data):
            local_marg_min = margin_min - original_data_off

            # calculate the average from scratch if it doesn't exist yet
            if data_avg is None or True:
                # data_avg = original_data[local_marg_min]
                # for i in range(local_marg_min + 1, local_marg_max):
                #     data_avg += original_data[i].copy()
                # data_avg /= margin_range
                data_avg = np.median(original_data[local_marg_min + 1 : local_marg_max], 0)
            
            # if it does exist, remove the preceding datas, and add the datas 
            # that need to be added
            else:
                # remove all preceding datas from average
                local_avg_start = data_avg_start - original_data_off
                for i in range(local_avg_start, local_marg_min):
                    data_avg -= original_data[i] / data_avg_range

                # adjust current avg weight to new range if changed
                local_avg_end = data_avg_end - original_data_off
                if data_avg_range != margin_range:
                    avg_weight_prev_numerator = data_avg_range - (
                        local_avg_start -
                        local_marg_min
                    )
                    avg_weight_numerator = margin_range - (
                        local_marg_max - 
                        local_avg_end
                    )
                    data_avg /= avg_weight_prev_numerator / data_avg_range
                    data_avg *= avg_weight_numerator

                # add new datas to average
                for i in range(local_avg_end, local_marg_max):
                    data_avg += original_data[i] / margin_range
            
            # remove unneeded datas from beginning of data list
            for _ in range(local_marg_min):
                original_data.pop(0)
                original_data_off += 1
            
            # update avg metadata
            data_avg_start = margin_min
            data_avg_end = margin_max
            data_avg_range = margin_range
            index_avged += 1
            avg_data.append(data_avg)

        # output the averaged vectors as a new fits file
        while len(avg_data) > 0:
            out_num = f"{index_written:0{out_name_digits}}"
            out_path = os.path.join(
                out_dir, 
                out_filename + f"{out_num}.avg.fits"
            )
            print(f"writing {out_path}..")
            fits.writeto(out_path, avg_data[0], overwrite=True)
            if out_paths is not None: out_paths.append(out_path)
            index_written += 1

            # pop data if not last iteration, so we rewrite the same file
            # multiple times at the end according to margin settings
            if not(index == file_count - 1 and index_written <= index):
                avg_data.pop(0)

        index += 1

    # apply the defined function to each data frame
    fits_file_iter(in_filepaths, iter_data, None, ** kwargs)