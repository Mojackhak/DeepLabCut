# Mojackhak Fork Release Contract

This document defines the packaging and release policy for the Mojackhak fork of DeepLabCut.

## Scope

This fork keeps the upstream distribution and import names:

- distribution name: `deeplabcut`
- import name: `deeplabcut`

This fork must not introduce a renamed package identity unless the downstream dependency graph is updated intentionally.

## Fork Identity

This repository publishes the Mojackhak-maintained PyTorch-based DeepLabCut fork.

Required package metadata:

- `url` points to `https://github.com/Mojackhak/DeepLabCut`
- project URLs include both the fork repository and the upstream repository
- package description explicitly identifies this build as the Mojackhak PyTorch fork

## Versioning

Use PEP 440 compatible post releases for fork packaging:

- upstream base: `3.0.0rc61`
- first fork release: `3.0.0rc61.post1`
- later fork releases: `3.0.0rc61.postN`

The PyTorch fork identity is expressed in metadata, tags, and release names rather than in the Python distribution name.

## Tags

Use annotated tags for release points.

Tag format:

- `mojackhak-deeplabcut-v<version>-pytorch`

Example:

- `mojackhak-deeplabcut-v3.0.0rc61.post1-pytorch`

## Release Artifacts

Each release tag must produce:

- source distribution
- wheel
- GitHub Release entry with uploaded artifacts

The release artifacts are the supported installation target for downstream environments.
Downstream repositories should not rely on `git+https://...@commit` as the primary installation path once wheel releases are available.

## Validation

Each release build must validate:

- `python -m build`
- `python -m twine check dist/*`
- `import deeplabcut`
- `import torch`
- `import torchvision`

If these checks fail, do not publish the release artifacts.
