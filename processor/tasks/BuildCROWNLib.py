import luigi
import os
from framework import Task, console
from CROWNBase import CROWNSandbox
import law

law.contrib.load("singularity")


# class BuildCROWNLib(Task):
class BuildCROWNLib(CROWNSandbox, Task):
    """
    Compile the CROWN shared libary to be used for all executables with the given configuration
    """

    # configuration variables
    build_dir = luigi.Parameter()
    install_dir = luigi.Parameter()
    friend_name = luigi.Parameter(default="ntuples")
    analysis = luigi.Parameter()

    def output(self):
        target = self.remote_target(f"{self.friend_name}/libCROWNLIB.so")
        return target

    def run(self):
        # get output file path
        output = self.output()
        # also use the tag for the local tarball creation
        _install_dir = os.path.abspath(
            os.path.join(
                str(self.install_dir),
                str(self.production_tag),
                f"crownlib_{self.friend_name}",
            )
        )
        _build_dir = os.path.abspath(
            os.path.join(
                str(self.build_dir),
                str(self.production_tag),
                f"crownlib_{self.friend_name}",
            )
        )
        _crown_path = os.path.abspath("CROWN")
        _compile_script = os.path.join(
            str(os.path.abspath("processor")),
            "tasks",
            "scripts",
            "compile_crown_lib.sh",
        )
        _local_libfile = os.path.join(_install_dir, "lib", output.basename)
        _analysis = str(self.analysis)
        if os.path.exists(os.path.join(_install_dir, output.basename)):
            console.log(f"lib already existing in tarball directory {_install_dir}")
            output.parent.touch()
            output.copy_from_local(_local_libfile)
        else:
            console.rule("Building new CROWNlib")
            # create build directory
            if not os.path.exists(_build_dir):
                os.makedirs(_build_dir)
            # same for the install directory
            if not os.path.exists(_install_dir):
                os.makedirs(_install_dir)

            # actual payload:
            console.rule("Starting cmake step for CROWNlib")
            console.log(f"Using CROWN {_crown_path}")
            console.log(f"Using build_directory {_build_dir}")
            console.log(f"Using install directory {_install_dir}")
            console.rule("")

            # run crown compilation script
            command = [
                "bash",
                _compile_script,
                _crown_path,  # CROWNFOLDER=$1
                _install_dir,  # INSTALLDIR=$2
                _build_dir,  # BUILDDIR=$3
                _analysis,  # ANALYSIS=$4
            ]
            self.run_command_readable(command)
            console.rule("Finished build of CROWNlib")
            output.parent.touch()
            output.copy_from_local(_local_libfile)
