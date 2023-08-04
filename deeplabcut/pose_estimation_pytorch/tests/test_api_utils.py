import os
import pytest
import numpy as np
import random

import deeplabcut.pose_estimation_pytorch as dlc
import deeplabcut.pose_estimation_pytorch.apis.utils as dlc_api_utils
import deeplabcut.utils.auxiliaryfunctions as dlc_auxfun

transform_dicts = [
    {
        "auto_padding": {
            "pad_height_divisor": 64,
            "pad_width_divisor": 27,
        }
    },
    {
        "resize": [512, 256],
    },
    {
        "covering": True,
        "gaussian_noise": 12.75,
        "hist_eq": True,
        "motion_blur": True,
        "normalize_images": True,
        "rotation": 30,
        "scale_jitter": [0.5, 1.25],
        "translation": 40,
        "auto_padding": {
            "pad_width_divisor": 64,
            "pad_height_divisor": 27,
        },
    },
    {
        "covering": True,
        "gaussian_noise": 100,
        "hist_eq": True,
        "motion_blur": True,
        "normalize_images": True,
        "rotation": 180,
        "scale_jitter": [0.03, 20],
        "translation": 300,
        "auto_padding": {
            "pad_width_divisor": 64,
            "pad_height_divisor": 27,
        },
    },
]


def _get_random_params(transform_idx):
    return (
        transform_dicts[transform_idx],
        (
            random.randint(100, 1000),
            random.randint(100, 1000),
        ),
        random.randint(1, 100),
        random.randint(1, 100),
    )


@pytest.mark.parametrize(
    "transform_dict, size_image, num_keypoints, num_animals",
    [_get_random_params(i) for i in range(4)],
)
def test_build_transforms(transform_dict, size_image, num_keypoints, num_animals):
    transform_bbox_aug = dlc_api_utils.build_transforms(
        transform_dict, augment_bbox=True
    )
    transform_no_bbox_aug = dlc_api_utils.build_transforms(
        transform_dict, augment_bbox=False
    )
    transform_inference = dlc_api_utils.build_inference_transform(
        transform_dict,
        augment_bbox=False,
    )

    w, h = size_image
    for i in range(10):
        test_image = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
        bboxes = np.random.randint(0, min(w - 1, h - 1), (num_animals, 4))
        bboxes[:, 2] = w - bboxes[:, 0]
        bboxes[:, 3] = h - bboxes[:, 1]
        keypoints = np.random.randint(0, min(w, h), (num_keypoints, 2))

        with pytest.raises(Exception):
            transformed = transform_no_bbox_aug(
                image=test_image, keypoints=keypoints.copy(), bboxes=bboxes.copy()
            )

        with pytest.raises(Exception):
            transformed = transform_inference(image=test_image)
            transformed = transform_inference(image=test_image, bboxes=bboxes.copy())
            transformed = transform_inference(
                image=test_image, keypoints=keypoints.copy(), bboxes=bboxes.copy()
            )

        transformed_with_bbox = transform_bbox_aug(
            image=test_image,
            keypoints=keypoints.copy(),
            bboxes=bboxes.copy(),
            bbox_labels=np.arange(num_animals),
        )
        transformed_without_bbox = transform_no_bbox_aug(
            image=test_image, keypoints=keypoints.copy()
        )
        transformed_inference = transform_inference(image=test_image, keypoints=[])

        if "resize" in transform_dict.keys():
            assert transformed_inference["image"].shape[:2] == (
                transform_dict["resize"][0],
                transform_dict["resize"][1],
            )
            assert transformed_with_bbox["image"].shape[:2] == (
                transform_dict["resize"][0],
                transform_dict["resize"][1],
            )
            assert transformed_without_bbox["image"].shape[:2] == (
                transform_dict["resize"][0],
                transform_dict["resize"][1],
            )

        if "auto_padding" in transform_dict.keys():
            modh, modw = (
                transform_dict["auto_padding"]["pad_height_divisor"],
                transform_dict["auto_padding"]["pad_width_divisor"],
            )
            assert transformed_inference["image"].shape[0] % modh == 0
            assert transformed_with_bbox["image"].shape[0] % modh == 0
            assert transformed_without_bbox["image"].shape[0] % modh == 0
            assert transformed_inference["image"].shape[1] % modw == 0
            assert transformed_with_bbox["image"].shape[1] % modw == 0
            assert transformed_without_bbox["image"].shape[1] % modw == 0

        assert len(transformed_with_bbox["keypoints"]) == len(keypoints)
        assert len(transformed_without_bbox["keypoints"]) == len(keypoints)
