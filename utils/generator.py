import tensorflow as tf
import cv2
import numpy as np
import os
import tifffile


class DataGenerator(tf.keras.utils.Sequence):
    def __init__(self, img_paths, gt_path, classes, batch_size=1, augment=True,
                 steps_per_epoch=None, seed=None, size=None, include=None,
                 exclude=None, class_weights=None):
        '''Initialize data generator for multi-band training
        Input images are sorted by file name. Their position in the file list
        serves as their image id in the generator.
        Parameters
        ----------
        img_paths : List of paths to folders containing the respective band
                    images
        gt_path : Path to the folder with the groundtruth images - classes need
                  to be encoded by integers
        classes : List of integer class labels to be found in groundtruth images 
        batch_size : Batch size, optional
        augment : Apply augmentation, optional
        steps_per_epoch : Number of batches to produce per epoch, optional
        seed : Random seed for alternating output order and applying
               augmentation, optional
        size : Proportion of the input data used for training, optional
        include : File containing image ids to be used when generating batches,
                  optional
        exclude : List of image ids to exclude when generating batches,
                  optional
        class_weights : List of weights containing one weight per class -
                        weigths are applied in order of classes list, optional
        Returns
        -------
        Data generator object
        '''
        # Either size, include or exclude must be specified
        assert ((size is None and include is None and exclude is not None)
                or (size is not None and include is None and exclude is None)
                or (size is None and include is not None and exclude is None))
        self.batch_size = batch_size
        self.augment = augment
        self.classes = classes
        self.class_num = len(classes)
        self.class_weights = class_weights
        self.steps_per_epoch = steps_per_epoch

        # problem info
        self.paths = self.__read_paths(img_paths, gt_path)
        in_shpe = self.__get_problem_info(self.paths)
        self.input_shape = in_shpe
        if self.class_weights is not None:
            error = 'Mismatch between defined and infered class size:'
            error += ' {} != {}'.format(len(self.class_weights), self.class_num)
            assert len(self.class_weights) == self.class_num, error

        self.rng = np.random.default_rng(seed)
        self.selected = self.__select_imgs(self.paths, size, include, exclude,
                                           self.rng)

        self.on_epoch_end()

    def __get_problem_info(self, paths):
        '''Infer input shape from ground truth image
        Parameters
        ----------
        paths : list of paths of the format [([input img,], gt_img)]
        Returns
        -------
        input shape
        '''
        # assume all images have the same shape
        img = tifffile.imread(paths[0][1])
        return (img.shape[0], img.shape[1], len(paths[0][0]))

    def __select_imgs(self, paths, size, include, exclude, rng):
        if size is not None:
            tmp = np.arange(len(paths))
            rng.shuffle(tmp)
            size = int(np.round(size * len(paths)))
            selected = tmp[:size]
        elif include is not None:
            with open(include, 'r') as f:
                selected = []
                for line in f:
                    selected.append(int(line))
        else:
            selected = [f for f in range(len(paths)) if f not in exclude]

        return selected

    def __read_paths(self, img_paths, gt_path):
        paths = []
        bands = []

        # list all images from all configured bands
        for img_path in img_paths:
            imgs = [os.path.join(img_path, f) for f in os.listdir(img_path)
                    if not f.startswith('._') and f.endswith('.tif')]
            imgs = sorted(imgs)
            if len(bands) == 0:
                bands = [[f] for f in imgs]
            else:
                for i, img in enumerate(imgs):
                    bands[i].append(img)

        # list ground truth images
        gts = [os.path.join(gt_path, f) for f in os.listdir(gt_path)
               if not f.startswith('._') and f.endswith('.tif')]
        gts = sorted(gts)

        # combine paths
        for imgs, gt in zip(bands, gts):
            gt_base = os.path.basename(gt)
            for img in imgs:
                img_base = os.path.basename(img)
                msg = 'Name mismatch {} - {}'.format(img_base, gt_base)
                assert img_base == gt_base, msg

            paths.append((imgs, gt))

        return paths

    def __len__(self):
        if self.steps_per_epoch is None:
            length = len(self.index) // self.batch_size
        else:
            length = self.steps_per_epoch
        return length

    def __getitem__(self, index):
        index = self.index[index * self.batch_size:
                           (index + 1) * self.batch_size]
        batch = [self.paths[k] for k in index]

        return self.__get_data(batch)

    def on_epoch_end(self):
        print('New Epoch')
        self.index = self.selected.copy()
        self.rng.shuffle(self.index)

    def __get_data(self, batch):
        X = []
        y = []
        weights = []

        for img_paths, gt_path in batch:
            # gt = cv2.imread(gt_path, cv2.IMREAD_GRAYSCALE)
            gt = tifffile.imread(gt_path)

            if self.augment:
                transform = None
                flip = None
                # select = self.rng.integers(0, 2, 3)
                select = self.rng.integers(0, 2, 2)
                if select[0]:
                    flip = self.choose_flip_augmentation(self.rng)
                if select[1]:
                    transform = self.choose_rotation_augmentation(gt, self.rng)
                # if select[2]:
                #    transform = self.choose_affine_transform_augmentation(
                #                                                gt, self.rng)
            # Create input image with containing all provided bands
            tmp = np.zeros(self.input_shape)
            for i, img_path in enumerate(img_paths):
                # img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                img = tifffile.imread(img_path)
                if self.augment:
                    img = self.apply_transform(img, flip, transform)
                # img = img.astype(np.float32) / 255.
                img = img.astype(np.float32)
                tmp[:, :, i] = img
            X.append(tmp)

            if self.augment:
                gt = self.apply_transform(gt, flip, transform, gt=True)
            gt_new = np.zeros(self.class_num * gt.shape[0] *
                              gt.shape[1]).reshape((*gt.shape, self.class_num))
            # set ground truth band - sorting is done based on class order
            # first band is class with lowest number, second band second
            # lowest, e.g., 0 - anything else, 1 - ditch, 2 - natural stream
            # band order [anything else, ditch, natural stream]
            for i, c in enumerate(self.classes):
                gt_new[gt == c, i] = 1
            y.append(gt_new.reshape((-1, self.class_num)))

            if self.class_weights is not None:
                w = np.zeros(gt.shape[0] * gt.shape[1]).reshape(*gt.shape)
                for i, c in enumerate(self.classes):
                    w[gt == c] = self.class_weights[i]
                weights.append(w.flatten())

        if self.class_weights is None:
            return np.array(X), np.array(y)
        else:
            return np.array(X), np.array(y), np.array(weights)

    def choose_flip_augmentation(self, rng):
        chosen_flip = None
        select = rng.integers(0, 4)

        if select == 0:
            chosen_flip = 0
        elif select == 1:
            chosen_flip = 1
        elif select == 2:
            chosen_flip = -1

        return chosen_flip

    def __flip_img(self, img, flip):
        if flip is None:
            return img
        else:
            return cv2.flip(img, flip)

    def choose_rotation_augmentation(self, img, rng):
        angle = rng.integers(0, 360)
        center = np.array(img.shape) / 2
        transform_matrix = cv2.getRotationMatrix2D(tuple(center), angle, 1)

        return transform_matrix

    def apply_transform(self, img, flip, transform, gt=False):
        if transform is None:
            return self.__flip_img(img, flip)
        else:
            return self.__warp_img(img, transform, gt)

    def __warp_img(self, img, transform, gt):
        y, x = img.shape[:2]

        borderValue = 0
        warped_img = cv2.warpAffine(img, transform, dsize=(x, y),
                                    borderValue=borderValue)
        if gt:
            warped_img = np.round(warped_img)

        return warped_img

    def choose_affine_transform_augmentation(self, img, rng,
                                             random_limits=(0.8, 1.1)):
        '''
        Creates an augmentation by computing a homography from three
        points in the image to three randomly generated points
        Note: base implementation from PHOCNet
        '''
        y, x = img.shape[:2]
        fx = float(x)
        fy = float(y)
        src_point = np.float32([[fx/2, fy/3, ],
                                [2*fx/3, 2*fy/3],
                                [fx/3, 2*fy/3]])
        random_shift = ((rng.random(6).reshape((3, 2)) - 0.5) * 2
                        * (random_limits[1]-random_limits[0])/2
                        + np.mean(random_limits))
        dst_point = src_point * random_shift.astype(np.float32)
        transform = cv2.getAffineTransform(src_point, dst_point)

        return transform