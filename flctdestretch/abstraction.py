import enum
import os
import time
from typing import Callable, TypedDict, Any

import numpy as np
from astropy.io import fits

from algorithm import reg_loop, DestretchLoopResult
from destretch_params import DestretchParams
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

def fits_file_iter(
        in_filepaths: list[os.PathLike],
        iter_func: Callable[[np.ndarray], None],
        index_schema: IndexSchema = IndexSchema.XY,
        z_index: int | None = 0
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
        image_data = load_image_data(path, index_schema, z_index)
        iter_func(image_data)

def fits_file_process_iter(
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
    index_schema: IndexSchema = kwargs.get("index_schema", IndexSchema.XYT)
    ref_method: RefMethod = kwargs.get("ref_method", OMargin(in_filepaths))

    # used to enforce the same resolution for all data files
    image_resolution = (-1,-1)

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
            image_data = load_image_data(path, index_schema)

        # ensure all data matches the first file's resolution
        if image_resolution[0] < 0:
            image_resolution = (
                image_data.shape[0], 
                image_data.shape[1]
            )
        elif (
            image_resolution[0] != image_data.shape[0] or 
            image_resolution[1] != image_data.shape[1]
        ): 
            raise Exception(f"Resolution mismatch for '{os.fspath(path)}'")

        # debug log
        # print(f"found {hdu_index} in {path}: {image_data.shape}")

        # get the reference image from the specified reference method
        reference_image = ref_method.get_reference(i)

        # perform image destretching
        print(f"processing image #{i}..")
        result = reg_loop(
            image_data,
            reference_image,
            kernel_sizes,
            mf=0.08,
            use_fft=True
        )

        # call the function specified by caller
        iter_func(result)

def destretch_files(
        in_filepaths: list[os.PathLike],
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
    out_name_digits: int = len(str(len(in_filepaths)))
    index: int = 0

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
        index += 1

    # iterate through file datas and call iter_process on destretched results
    fits_file_process_iter(in_filepaths, iter_process, ** kwargs)

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

    # ensure output directory exists
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # define the processing to calculate and store the offset files
    def process_iter(result: DestretchLoopResult):
        nonlocal index

        # use final displacement sum 'disp_sum' - 'rdisp_sum'
        _, disp_sum, rdisp_sum, _ = result
        offsets = disp_sum - rdisp_sum
        offsets = IndexSchema.convert(offsets, IndexSchema.TYX, IndexSchema.XYT)

        # output the vectors as a new fits file
        out_num = f"{index:0{out_name_digits}}"
        out_path = os.path.join(out_dir, out_filename + f"{out_num}.off.fits")
        fits.writeto(out_path, offsets, overwrite=True)
        index += 1
    
    # use default previousRef method if not specified
    kwargs["ref_method"] = kwargs.get("ref_method", PreviousRef(in_filepaths))

    # iterate over data in files
    fits_file_process_iter(in_filepaths, process_iter, ** kwargs)

def calc_rolling_mean(
        in_filepaths: list[os.PathLike],
        out_dir: os.PathLike,
        out_filename: str = "offsets",
        margin_left: int = 5,
        margin_right: int = 5,
        end_behavior: MarginEndBehavior = MarginEndBehavior.KEEP_RANGE
    )-> None:
    """
    TODO - unfinished, function needs to be finished
    """

    # number of digits needed to accurately order the output files
    out_name_digits: int = len(str(len(in_filepaths)))
    index: int = 0
    index_written: int = 0

    file_count = len(in_filepaths)
    original_data: list[np.ndarray]
    original_data_off: int = 0

    def iter_data(data: np.ndarray):
        nonlocal index, index_written, original_data_off

        # calculate the local margin values
        margin_min = index - margin_left
        margin_max = index + margin_right + 1
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

        # remove datas who are no longer needed
        # off_increment = margin_min - original_data_off
        # original_data_off = margin_min
        # for _ in range(off_increment):
        #     original_data.pop(0)

        local_index = index - original_data_off
        if local_index >= len(original_data):
            original_data.append(data)
        
        avg: np.ndarray = ...

        # output the vectors as a new fits file
        out_num = f"{index:0{out_name_digits}}"
        out_path = os.path.join(out_dir, out_filename + f"{out_num}.off.fits")
        fits.writeto(out_path, avg, overwrite=True)
        index += 1

    fits_file_iter(in_filepaths, iter_data, IndexSchema.XYT, None)