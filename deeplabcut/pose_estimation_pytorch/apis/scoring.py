#
# DeepLabCut Toolbox (deeplabcut.org)
# © A. & M.W. Mathis Labs
# https://github.com/DeepLabCut/DeepLabCut
#
# Please see AUTHORS for contributors.
# https://github.com/DeepLabCut/DeepLabCut/blob/master/AUTHORS
#
# Licensed under GNU Lesser General Public License v3.0
#
from __future__ import annotations

import numpy as np

from deeplabcut.pose_estimation_pytorch.post_processing import (
    rmse_match_prediction_to_gt,
)
from deeplabcut.pose_estimation_tensorflow.lib.inferenceutils import (
    Assembly,
    evaluate_assembly,
)


def get_scores(
    poses: dict[str, np.ndarray],
    ground_truth: dict[str, np.ndarray],
    unique_bodypart_poses: dict[str, np.ndarray] | None = None,
    unique_bodypart_gt: dict[str, np.ndarray] | None = None,
    pcutoff: float = -1,
) -> dict[str, float]:
    """Computes for the different scores given the ground truth and the predictions.

    The poses and ground truth should already be aligned to the ground truth (the scores
    will be computed assuming individual i in the poses matches to individual i in the
    ground truth)

    The different scores computed are based on the COCO metrics: https://cocodataset.org/#keypoints-eval
    RMSE (Root Mean Square Error)
    OKS mAP (Mean Average Precision)
    OKS mAR (Mean Average Recall)

    Args:
        poses: the predicted poses for each image in the format
            {'image': keypoints with shape (num_individuals, num_keypoints, 3)}
        ground_truth: ground truth keypoints for each image in the format
            {'image': keypoints with shape (num_individuals, num_keypoints, 3)}
        pcutoff: the pcutoff used to use
        unique_bodypart_poses: the predicted poses for unique bodyparts
        unique_bodypart_gt: the ground truth for unique bodyparts

    Returns:
        a dictionary of scores containign the following keys
            ['rmse', 'rmse_pcutoff', 'mAP', 'mAR', 'mAP_pcutoff', 'mAR_pcutoff']

    Examples:
        >>> # Define the p-cutoff, prediction, and target DataFrames
        >>> pcutoff = 0.5
        >>> prediction = {"img0": [[[0.1, 0.5, 0.4], [5.2, 3.3, 0.9]], ...], ...}
        >>> ground_truth = {"img0": [[[0, 0], [5, 3]], ...], ...}
        >>> # Compute the scores
        >>> scores = get_scores(poses, ground_truth, pcutoff)
        >>> print(scores)
        {
            'rmse': 0.156,
            'rmse_pcutoff': 0.115,
            'mAP': 84.2,
            'mAR': 74.5,
            'mAP_pcutoff': 91.3,
            'mAR_pcutoff': 82.5
        }  # Sample output scores
    """
    if not len(poses) == len(ground_truth):
        raise ValueError(
            "The prediction an ground truth dicts must contain the same number of "
            f"images (poses={len(poses)}, gt={len(ground_truth)})"
        )

    image_paths = list(poses)
    pred_poses = build_keypoint_array(poses, image_paths)[..., :3].reshape((-1, 3))
    gt_poses = build_keypoint_array(ground_truth, image_paths).reshape((-1, 2))
    if unique_bodypart_poses is not None:
        pred_poses = np.concatenate(
            [
                pred_poses,
                build_keypoint_array(unique_bodypart_poses, image_paths)[
                    ..., :3
                ].reshape((-1, 3)),
            ]
        )
        gt_poses = np.concatenate(
            [
                gt_poses,
                build_keypoint_array(unique_bodypart_gt, image_paths).reshape((-1, 2)),
            ]
        )

    rmse, rmse_pcutoff = compute_rmse(pred_poses, gt_poses, pcutoff=pcutoff)

    oks = compute_oks(poses, ground_truth, pcutoff=None)
    oks_pcutoff = compute_oks(poses, ground_truth, pcutoff=pcutoff)

    return {
        "rmse": rmse,
        "rmse_pcutoff": rmse_pcutoff,
        "mAP": 100 * oks["mAP"],
        "mAR": 100 * oks["mAR"],
        "mAP_pcutoff": 100 * oks_pcutoff["mAP"],
        "mAR_pcutoff": 100 * oks_pcutoff["mAR"],
    }


def build_keypoint_array(
    keypoints: dict[str, np.ndarray], keys: list[str]
) -> np.ndarray:
    """Stacks arrays of keypoints in a given order

    Args:
        keypoints: the keypoint arrays to stack
        keys: the order of keys to use to stack the arrays

    Returns:
        the stacked arrays
    """
    image_keypoints = []
    for image_key in keys:
        image_keypoints.append(keypoints[image_key])
    return np.stack(image_keypoints)


def compute_rmse(
    pred: np.ndarray, ground_truth: np.ndarray, pcutoff: float = -1
) -> tuple[float, float]:
    """Computes the root mean square error (rmse) for predictions vs the ground truth labels

    Assumes that poses have been aligned to ground truth (keypoint i in the pred array
    corresponds to keypoint i in the ground_truth array)

    Args:
        pred: (n, 3) the predicted keypoints in format x, y, score
        ground_truth: (n, 2) the ground truth keypoints
        pcutoff: the pcutoff score

    Returns:
        the RMSE and RMSE with pcutoff values
    """
    if pred.shape[0] != ground_truth.shape[0]:
        raise ValueError(
            "Prediction and target arrays must have same number of elements!"
        )

    mask = pred[:, 2] >= pcutoff
    square_distances = (pred[:, :2] - ground_truth) ** 2
    mean_square_errors = np.sum(square_distances, axis=1)
    rmse = np.nanmean(np.sqrt(mean_square_errors)).item()
    rmse_p = np.nanmean(np.sqrt(mean_square_errors[mask])).item()
    return rmse, rmse_p


def compute_oks(
    pred: dict[str, np.array],
    ground_truth: dict[str, np.array],
    oks_sigma=0.1,
    margin=0,
    symmetric_kpts=None,
    pcutoff: float | None = None,
) -> dict:
    """Computes the

    Assumes that poses have been aligned to ground truth (for an image, individual i in
    the pred array corresponds to individual i in the ground_truth array)

    Args:
        pred: the predicted poses for each image in the format
            {'image': keypoints with shape (num_individuals, num_keypoints, 3)}
        ground_truth: ground truth keypoints for each image in the format
            {'image': keypoints with shape (num_individuals, num_keypoints, 3)}
        oks_sigma: sigma for OKS computation.
        margin: margin used for bbox computation.
        symmetric_kpts: TODO: not supported yet
        pcutoff: the pcutoff used to use

    Returns:
        the OKS scores
    """
    masked_pred = {}
    for image_path, keypoints_with_scores in pred.items():
        keypoints = keypoints_with_scores[:, :, :2].copy()
        if pcutoff is not None:
            keypoints[keypoints_with_scores[:, :, 2] < pcutoff] = np.nan
        masked_pred[image_path] = keypoints

    assemblies_pred = build_assemblies(masked_pred)
    assemblies_gt = build_assemblies(ground_truth)
    return evaluate_assembly(
        assemblies_pred,
        assemblies_gt,
        oks_sigma,
        margin=margin,
        symmetric_kpts=symmetric_kpts,
    )


def build_assemblies(poses: dict[str, np.ndarray]) -> dict[str, list[Assembly]]:
    """
    Builds assemblies from a pose array

    Args:
        poses: {image: keypoints with shape (num_individuals, num_keypoints, 2)}

    Returns:
        the assemblies for each image
    """
    assemblies = {}
    for image_path, keypoints in poses.items():
        image_assemblies = []
        for idv_bodyparts in keypoints:
            assembly = Assembly.from_array(idv_bodyparts)
            if len(assembly):
                image_assemblies.append(assembly)

        assemblies[image_path] = image_assemblies

    return assemblies


def align_predicted_individuals_to_gt(
    predictions: dict[str, np.ndarray], ground_truth: dict[str, np.ndarray]
) -> dict[str, np.ndarray]:
    """TODO: implement with OKS as well
    Uses RMSE to match predicted individuals to frame annotations for a batch of
    frames. This method is preferred to OKS, as OKS needs at least 2 annotated
    keypoints per animal (to compute area)

    The poses array is modified in-place, where the order of elements are
    swapped in 2nd dimension (individuals) such that the keypoints in predictions[img][i]
    is matched to the ground truth annotations of df_target[img][i]

    Args:
        predictions: {image_path: predicted pose of shape (individual, keypoints, 3)}
        ground_truth: the ground truth annotations to align

    Returns:
        the same dictionary as the input predictions, but where the "individual" axis
        for each prediction is aligned with the ground truth data
    """
    matched_poses = {}
    for image, pose in predictions.items():
        gt_pose = mask_invisible(ground_truth[image], mask_value=-1)
        gt_pose = np.nan_to_num(gt_pose, nan=-1)
        match_individuals = rmse_match_prediction_to_gt(pose, gt_pose)
        matched_poses[image] = pose[match_individuals]

    return matched_poses


def mask_invisible(
    keypoints: np.ndarray, mask_value: int | float | np.nan = -1.0
) -> np.ndarray:
    """
    Masks keypoints that are not visible in an array.

    Args:
        keypoints: a keypoint array of shape (..., 3), where the last axis contains
            the x, y and visibility values (0 == invisible)
        mask_value: the value to give to the keypoints that are masked

    Returns:
        a keypoint array of shape (..., 2) with the coordinates of the keypoints marked
        as invisible replaced with the mask value
    """
    keypoints = keypoints.copy()
    visibility = keypoints[..., 2] == 0
    keypoints[visibility, 0] = mask_value
    keypoints[visibility, 1] = mask_value
    return keypoints[..., :2]
