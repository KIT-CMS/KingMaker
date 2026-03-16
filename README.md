# KingMaker

KingMaker is the workflow management for producing ntuples with the [CROWN](https://github.com/KIT-CMS/CROWN) framework. The workflow management is based on [law](https://github.com/riga/law), which is using [luigi](https://github.com/spotify/luigi) as backend.

**⚠ Important: A detailed description of the KingMaker workflow to produce NTuples can be found in the [CROWN documentation](https://crown.readthedocs.io/en/latest/kingmaker.html#).**


## 🛠 Infrastructure & Containers

KingMaker can runs within container environments to ensure reproducibility.

* **Container Images and Environments**: Dockerfiles and Conda environment specifications are located in the [`/containers`](./containers) directory.
* **Usage**: For instructions on building custom images or using existing ones from CVMFS, see the [Container Documentation](./containers/README.md).
