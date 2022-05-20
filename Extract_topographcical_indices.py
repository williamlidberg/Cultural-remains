import os
import argparse
import tifffile
import pathlib
import whitebox
wbt = whitebox.WhiteboxTools()


class Topographical_indices:
    def __init__(self, temp_dir):
        self.temp_dir = temp_dir

    def hillshade(self, input_path, normalized_hillshade):
        wbt.multidirectional_hillshade(
        dem = input_path, 
        output = self.temp_dir + os.path.basename(input_path), 
        altitude=45.0, 
        zfactor=None, 
        full_mode=False)
        img = tifffile.imread(self.temp_dir + os.path.basename(input_path))
        normed_shade = img/32767 # hillshade is a 16 bit signed integer file but only values between 0 and 32767 are used for hillshades
        tifffile.imwrite(normalized_hillshade, normed_shade.astype('float32'))

    def slope(self, input_path, normalized_slope):
        wbt.slope(
        dem = input_path, 
        output = self.temp_dir + os.path.basename(input_path), 
        zfactor=None, 
        units= 'degrees')
        img = tifffile.imread(self.temp_dir + os.path.basename(input_path))
        normed_slope = img/90 # no slope can be flatter than 0 degrees or steeper than 90 degrees
        tifffile.imwrite(normalized_slope, normed_slope.astype('float32'))

    def high_pass_median_filter(self, input_path, normalized_hpmf):
        wbt.high_pass_median_filter(
        i = input_path, 
        output =  self.temp_dir + os.path.basename(input_path), 
        filterx=11, 
        filtery=11, 
        sig_digits=2)
        img = tifffile.imread(self.temp_dir + os.path.basename(input_path))
        normed_hpmf = (img--1)/(2--1) 
        tifffile.imwrite(normalized_hpmf, normed_hpmf.astype('float32'))

    def spherical_std_dev_of_normals(self, input_path, normalized_stdon):
        wbt.spherical_std_dev_of_normals(
        dem = input_path, 
        output = self.temp_dir + os.path.basename(input_path), 
        filter=5)
        img = tifffile.imread(self.temp_dir + os.path.basename(input_path))
        normed_stdon = img/30 
        tifffile.imwrite(normalized_stdon, normed_stdon.astype('float32'))

def clean_temp(temp_dir):
    for root, dir, fs in os.walk(temp_dir):
        for f in fs:
            os.remove(os.path.join(root, f))


def main(temp_dir, input_path, output_path_hillshade, output_path_slope, output_path_hpmf, output_path_stdon):
#    setup paths
    if not os.path.exists(input_path):
        raise ValueError('Input path does not exist: {}'.format(input_path))
    if os.path.isdir(input_path):
        imgs = [os.path.join(input_path, f) for f in os.listdir(input_path)
                if f.endswith('.tif')]
    else:
        imgs = [input_path] 
    for img_path in imgs:
        img_name = os.path.basename(img_path).split('.')[0]
        
        # outputs 
        hillshade = os.path.join(output_path_hillshade,'{}.{}'.format(img_name, 'tif'))
        slope = os.path.join(output_path_slope,'{}.{}'.format(img_name, 'tif'))
        high_pass_median_filter = os.path.join(output_path_hpmf,'{}.{}'.format(img_name, 'tif'))
        spherical_std_dev_of_normals = os.path.join(output_path_stdon,'{}.{}'.format(img_name, 'tif'))

        topographical = Topographical_indices(temp_dir)
        clean_temp(temp_dir)
        topographical.hillshade(img_path, hillshade)
        clean_temp(temp_dir)
        topographical.slope(img_path, slope)
        clean_temp(temp_dir)
        topographical.high_pass_median_filter(img_path, high_pass_median_filter)
        clean_temp(temp_dir)
        topographical.spherical_std_dev_of_normals(img_path, spherical_std_dev_of_normals)
        clean_temp(temp_dir)

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
                       description='Extract topographical indicies '
                                   'image(s)',
                       formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('temp_dir', help= 'path to a temperary directory')
    parser.add_argument('input_path', help='Path to dem or folder of dems')
    parser.add_argument('output_path_hillshade', help = 'directory to store hillshade images')
    parser.add_argument('output_path_slope', help = 'directory to store slope images')
    parser.add_argument('output_path_hpmf', help = 'directory to store hpmf images')
    parser.add_argument('output_path_stdon', help='directory to store stdon images')
    args = vars(parser.parse_args())
    main(**args)