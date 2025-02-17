## Imports and Initialization -------------------------------------------------|
print("Importing dependencies... ")

from pathlib import Path
import os
import numpy as np

# .fits file format parsing
import astropy.io.fits
from astropy.io.fits import HDUList, ImageHDU

# data visualization
import matplotlib.pyplot as plt
import matplotlib.animation
from matplotlib.figure import Figure
from matplotlib.image import AxesImage

# plot rendering backend
matplotlib.use("tkagg")
plt.rcParams['toolbar'] = 'None'

# internal
import algorithm as destretch


## Data Initialization --------------------------------------------------------|

# load our image data
data_filepath: Path = Path(os.getcwd()).joinpath("examples", "media", "test.fits")
print("Loading test data file '" + str(data_filepath) + "'... ")
data: HDUList = astropy.io.fits.open(data_filepath)
image_data_0: ImageHDU = data[0]
print("Loaded! ")

# test data ?? TODO explain better
test_data: np.ndarray = image_data_0.data

# process image ??
print("Preprocessing image data... ")
test_data /= np.mean(test_data)
test_data -= 1

# median image for y axis ??
test_median_y = np.median(test_data, axis=0)
print("Done! ")


## Perform Destretching -------------------------------------------------------|

# I think the sizes of each sub-image to relocate via destretch ??
kernel_sizes: np.ndarray[np.int64] = np.array([64])

# ?? TODO
scene = np.moveaxis(test_data.copy(), 0, -1)

print("Destretching images... ")
# this goes through each image in the data and applies the destretching 
# algorithm and stores the result
result = destretch.reg_loop_series(
	scene, 
	test_median_y, 
	kernel_sizes, 
	mf=0.08, 
	use_fft=True 
)

# deconstruct the results into meaningful typed variables
answer: np.ndarray[np.float64]
display: np.ndarray[np.float64]
r_display: np.ndarray[np.float64]
destretch_info: destretch.DestretchParams
(answer, display, r_display, destretch_info) = result
print("Done!")


## Visualize Destretch Data ---------------------------------------------------|

print("Visualizing data... ")
r_index: int = 3
display_delta = (display.T - r_display.T).T
display_delta_t = np.sqrt(display_delta[0] ** 2 + display_delta[1] ** 2)

plt.figure(figsize=(12,10), facecolor="w")

plt.subplot(2, 2, 1)
plt.imshow(test_data[r_index], origin="lower", cmap="binary_r")
plt.title("Raw Scene")
plt.colorbar()
plt.xticks([])
plt.yticks([])

plt.subplot(2, 2, 2)
plt.imshow(
	test_data[r_index] - test_median_y, origin="lower", cmap="binary_r", 
	#vmin=-0.1, vmax=0.1
)
plt.title("Raw Difference")
plt.colorbar()
plt.xticks([])
plt.yticks([])

plt.subplot(2, 2, 3)
plt.imshow(display_delta_t[:, :, r_index], origin="lower", cmap="binary_r")
plt.title("Destretch Vectors")
plt.colorbar()
plt.xticks([])
plt.yticks([])
#plt.quiver(
#	np.arange(destretch_info.cpx)[::2], 
#	np.arange(destretch_info.cpy)[::2],
#	display_delta[0, ::2, ::2, r_index],
#	display_delta[1, ::2, ::2, r_index],
#	display_delta[::2, ::2, r_index],
#	cmap="inferno_r"
#)

plt.subplot(2, 2, 4)
plt.imshow(
	answer[:, :, r_index] - test_median_y,
	origin="lower", cmap="binary_r", 
	#vmin=-0.01, vmax=0.01
)
plt.colorbar()
plt.xticks([])
plt.yticks([])
plt.title("Destretched Difference")
plt.tight_layout()
plt.show()


## Visualize Data -------------------------------------------------------------|

# create a figure to render our data onto
figure: Figure = plt.figure(figsize=(5,4), dpi=169)

# get handle to the specific subplot to render
plot_pre = plt.subplot(1, 2, 1)
plot_pre.set_title("Before FLCT Destretching")
plot_pre.set_xlim(0, 1000)
plot_pre.set_ylim(0, 1000)

# hide x and y axis numbers since they are pretty much meaningless for images
plot_pre.set_xticks([])
plot_pre.set_yticks([])

# create image sequences for our original image data
frame_original: AxesImage = plt.imshow(
	test_data[0], origin="lower", cmap="copper"
)
frame_original.set_rasterized(True)
frame_original.set_animated(True)

# define the function to animate each frame
def draw_frame_original(index: int) -> AxesImage:
	frame_original.set_data(test_data[index])
	return frame_original

# create an animation to view the image data in succession
animation_original = matplotlib.animation.FuncAnimation(
	figure, draw_frame_original, 
	frames=len(test_data), 
	interval=100
)

# arrange sublot and get handle
plot_post = plt.subplot(1, 2, 2)
plot_post.set_title("After FLCT Destretching")
plot_post.set_xlim(0, 1000)
plot_post.set_ylim(0, 1000)

# hide x and y axis numbers since they are pretty much meaningless for images
plot_post.set_xticks([])
plot_post.set_yticks([])

# create the images for rendering the new destretched image data
frame_destretched = plt.imshow(
	answer[:, :, 0], origin="lower", cmap="copper"
)
frame_destretched.set_rasterized(True)
frame_destretched.set_animated(True)
images_sequence_destretched: np.ndarray[AxesImage] = np.empty(11, dtype=AxesImage)
for i in range(len(images_sequence_destretched)):
	images_sequence_destretched[i] = answer[:, :, i].copy()

# set the data for each frame of the new 
def draw_frame_destretched(index: int) -> AxesImage:
	frame_destretched.set_data(images_sequence_destretched[index])
	return frame_destretched

# create a new animation to display the image data resulting from 
# the destretching
animation_destretched = matplotlib.animation.FuncAnimation(
	figure, draw_frame_destretched, 
	frames=len(images_sequence_destretched), 
	interval=100
)

# display the visualization
plt.show()

print("Demo Complete")