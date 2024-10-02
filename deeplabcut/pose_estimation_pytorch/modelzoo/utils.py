#
# DeepLabCut Toolbox (deeplabcut.org)
# © A. & M.W. Mathis Labs
# https://github.com/DeepLabCut/DeepLabCut
#
# Please see AUTHORS for contributors.
# https://github.com/DeepLabCut/DeepLabCut/blob/main/AUTHORS
#
# Licensed under GNU Lesser General Public License v3.0
#
import inspect
import subprocess
import warnings
from pathlib import Path

import torch
from dlclibrary import download_huggingface_model

import deeplabcut.pose_estimation_pytorch.config.utils as config_utils
from deeplabcut.pose_estimation_pytorch.config.make_pose_config import add_metadata
from deeplabcut.utils import auxiliaryfunctions


def get_model_configs_folder_path() -> Path:
    """Returns: the folder containing the SuperAnimal model configuration files"""
    return Path(auxiliaryfunctions.get_deeplabcut_path()) / "modelzoo" / "model_configs"


def get_project_configs_folder_path() -> Path:
    """Returns: the folder containing the SuperAnimal project configuration files"""
    return (
        Path(auxiliaryfunctions.get_deeplabcut_path()) / "modelzoo" / "project_configs"
    )


def get_snapshot_folder_path() -> Path:
    """Returns: the path to the folder containing the SuperAnimal model snapshots"""
    return Path(auxiliaryfunctions.get_deeplabcut_path()) / "modelzoo" / "checkpoints"


def get_super_animal_model_config_path(model_name: str) -> Path:
    """Gets the path to the configuration file for a SuperAnimal model.

    Args:
        model_name: The name of the model for which to get the path.

    Returns:
        The path to the config file for a SuperAnimal model.
    """
    return get_model_configs_folder_path() / f"{model_name}.yaml"


def get_super_animal_project_config_path(super_animal: str) -> Path:
    """Gets the path to a SuperAnimal project configuration file.

    Args:
        super_animal: The name of the SuperAnimal for which to get the config path.

    Returns:
        The path to the config file for a SuperAnimal project.
    """
    return get_project_configs_folder_path() / f"{super_animal}.yaml"


def get_super_animal_snapshot_path(
    dataset: str,
    model_name: str,
    download: bool = True,
) -> Path:
    """Gets the path to the snapshot containing SuperAnimal model weights.

    Args:
        dataset: The name of the SuperAnimal dataset.
        model_name: The name of the model.
        download: Whether to download the weights if they aren't already there.

    Returns:
        The path to the weights for a SuperAnimal model.
    """
    model_path = get_snapshot_folder_path() / f"{dataset}_{model_name}.pt"
    if download and not model_path.exists():
        download_super_animal_snapshot(dataset, model_name)

    return model_path


def load_super_animal_config(
    super_animal: str,
    model_name: str,
    detector_name: str | None = None,
) -> dict:
    """Loads the model configuration file for a model, detector and SuperAnimal

    Args:
        super_animal: The name of the SuperAnimal for which to create the model config.
        model_name: The name of the model for which to create the model config.
        detector_name: The name of the detector for which to create the model config.

    Returns:
        The model configuration for a SuperAnimal-pretrained model.
    """
    project_cfg_path = get_super_animal_project_config_path(super_animal=super_animal)
    project_config = config_utils.read_config_as_dict(project_cfg_path)

    model_cfg_path = get_super_animal_model_config_path(model_name=model_name)
    model_config = config_utils.read_config_as_dict(model_cfg_path)
    model_config = add_metadata(project_config, model_config, model_cfg_path)

    if detector_name is None:
        model_config["method"] = "BU"
    else:
        detector_cfg_path = get_super_animal_model_config_path(model_name=detector_name)
        detector_cfg = config_utils.read_config_as_dict(detector_cfg_path)
        model_config["method"] = "TD"
        model_config["detector"] = detector_cfg
    return model_config


def download_super_animal_snapshot(dataset: str, model_name: str) -> Path:
    """Downloads a SuperAnimal snapshot

    Args:
        dataset: The name of the SuperAnimal dataset for which to download a snapshot.
        model_name: The name of the model for which to download a snapshot.

    Returns:
        The path to the downloaded snapshot.

    Raises:
        RuntimeError if the model fails to download.
    """
    snapshot_dir = get_snapshot_folder_path()
    model_name = f"{dataset}_{model_name}"
    model_path = snapshot_dir / f"{model_name}.pt"

    # FIXME(niels) - Temporary fix, update the filenames on HuggingFace
    rename_mapping = None
    if "hrnet_w32" in model_name:
        rename_mapping = {"pose_model.pth": f"{model_name}.pt"}
    elif "fasterrcnn_resnet50_fpn_v2" in model_name:
        rename_mapping = {"detector.pt": f"{model_name}.pt"}

    download_huggingface_model(
        model_name,
        target_dir=str(snapshot_dir),
        rename_mapping=rename_mapping,
    )

    if not model_path.exists():
        raise RuntimeError(f"Failed to download {model_name} to {model_path}")

    # FIXME(niels) - Temporary fix, upload parsed checkpoints to HuggingFace
    if "hrnet_w32" in model_name or "fasterrcnn_resnet50_fpn_v2" in model_name:
        _parse_snapshot(model_path, device="cpu")

    return snapshot_dir / f"{model_name}.pt"


def get_gpu_memory_map():
    """Get the current gpu usage."""
    result = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,nounits,noheader"],
        encoding="utf-8",
    )
    gpu_memory = [int(x) for x in result.strip().split("\n")]
    gpu_memory_map = dict(zip(range(len(gpu_memory)), gpu_memory))

    return gpu_memory_map


def select_device():
    if torch.cuda.is_available():
        return torch.device(f"cuda:0")
    else:
        return torch.device("cpu")


def raise_warning_if_called_directly():
    current_frame = inspect.currentframe()
    caller_frame = inspect.getouterframes(current_frame, 2)
    caller_name = caller_frame[1].filename

    if not "pose_estimation_" in caller_name:
        warnings.warn(
            f"{caller_name} is intended for internal use only and should not be called directly.",
            UserWarning,
        )


def update_config(config, max_individuals, device):
    config = config_utils.replace_default_values(
        config,
        num_bodyparts=len(config["metadata"]["bodyparts"]),
        num_individuals=max_individuals,
        backbone_output_channels=config["model"]["backbone_output_channels"],
    )
    config["metadata"]["individuals"] = [f"animal{i}" for i in range(max_individuals)]

    config["device"] = device
    if "detector" in config:
        config["detector"]["device"] = device

    config_utils.pretty_print(config)
    return config


def _parse_snapshot(snapshot_path: Path, device: str, print_keys: bool = False) -> None:
    """FIXME: A new snapshot should be uploaded and used"""
    def _map_model_keys(state_dict: dict) -> dict:
        updated_dict = {}
        for k, v in state_dict.items():
            if not (
                k.startswith("backbone.model.downsamp_modules.")
                or k.startswith("backbone.model.final_layer")
                or k.startswith("backbone.model.classifier")
            ):
                parts = k.split(".")
                if parts[:4] == ["heads", "bodypart", "heatmap_head", "model"]:
                    parts[3] = "deconv_layers.0"
                updated_dict[".".join(parts)] = v
        return updated_dict

    snapshot = torch.load(snapshot_path, map_location=device)
    if print_keys:
        print(5 * "-----\n")
        print(snapshot.stem + " keys")
        for name, _ in snapshot["model_state_dict"].items():
            print(f"  * {name}")
        print()

    torch.save(
        dict(
            model=_map_model_keys(snapshot["model_state_dict"]),
            metadata=dict(epoch=0),
        ),
        snapshot_path,
    )
