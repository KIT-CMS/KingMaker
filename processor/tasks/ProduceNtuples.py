import os
import luigi
import ast
import yaml
from CROWNBase import ProduceBase
from collections import defaultdict
from framework import console
from CROWNFriend import CROWNFriend
from CROWNMain import CROWNRun


class ProduceNtuples(ProduceBase):
    """
    collective task to trigger friend production for a list of samples,
    if the samples are not already present, trigger ntuple production first
    """

    friend_config = luigi.Parameter(default="")
    friend_name = luigi.Parameter(default="")
    friend_mapping = luigi.Parameter(default="{}")

    def derive_mapping(self, read_only=False):
        if read_only:
            if isinstance(self.friend_mapping, str):
                if os.path.isfile(self.friend_mapping):
                    with open(self.friend_mapping) as stream:
                        self.friend_mapping = yaml.safe_load(stream)
                else:
                    value = self.friend_mapping.strip()
                    parsed = ast.literal_eval(value)
                    if isinstance(parsed, dict):
                        self.friend_mapping = parsed
                    else:
                        raise ValueError(
                            f"friend_mapping '{self.friend_mapping}' is not a valid dictionary literal."
                        )
            return

        if isinstance(self.friend_mapping, str):
            value = self.friend_mapping.strip()
            try:
                parsed = ast.literal_eval(value)

                # enforce priority order
                if isinstance(parsed, dict):
                    parsed_map = parsed
                elif isinstance(parsed, str):
                    parsed_map = parsed
                else:
                    # anything else (int, float, tuple, etc.) -> coerce to string
                    parsed_map = str(parsed)
            except (ValueError, SyntaxError):
                parsed_map = value  # fallback: raw string
        else:
            parsed_map = self.friend_mapping

        if isinstance(parsed_map, str):
            with open(self.friend_mapping) as stream:
                parsed_map_data = yaml.safe_load(stream)
        elif parsed_map == {}:
            parsed_map_data = defaultdict(dict)
        else:
            parsed_map_data = parsed_map

        if (
            self.friend_name == ""
            and parsed_map_data[self.friend_config].get("friend_name") is None
        ):
            self.friend_name = self.friend_config
        else:
            if self.friend_name != "":
                parsed_map_data[self.friend_config]["friend_name"] = self.friend_name

        self.friend_mapping = self.normalize_configs(parsed_map_data)

    def normalize_configs(self, configs: dict) -> dict:
        """
        Normalize config dictionary:
        - If a config value is None -> replace with {}
        - If a required config is missing -> add it as {}
        - Add friend_name=<key> if not present
        """

        # First pass: normalize existing entries
        for key in list(configs.keys()):
            if configs[key] is None:
                configs[key] = {}

        # Second pass: ensure required configs exist
        for key, cfg in list(configs.items()):
            requires = cfg.get("requires", [])

            for dep in requires:
                if dep not in configs or configs[dep] is None:
                    configs[dep] = {}

        # Third pass: ensure friend_name exists
        for key, cfg in configs.items():
            cfg.setdefault("friend_name", key)

        return configs

    def recursive_check(self, map, key, visited):
        for k in map[key].get("requires", []):
            if k not in visited:
                visited.append(k)
                self.recursive_check(map, k, visited)
            else:
                raise Exception(
                    f"Friend dependency loop detected for {key}: {visited+[k]}"
                )

    def requires(self):
        if self.friend_config != "" and self.friend_mapping != "{}":
            self.derive_mapping()
            self.recursive_check(
                self.friend_mapping, self.friend_config, [self.friend_config]
            )
        elif self.friend_mapping != "{}" and self.friend_config == "":
            self.derive_mapping(read_only=True)
            for key in self.friend_mapping.keys():
                self.recursive_check(self.friend_mapping, key, [key])

        self.sanitize_scopes()
        self.sanitize_shifts()
        if not self.silent:
            console.rule("")
            console.log(f"Production tag: {self.production_tag}")
            console.log(f"Analysis: {self.analysis}")
            console.log(f"Config: {self.config}")
            console.log(f"Shifts: {self.shifts}")
            console.log(f"Scopes: {self.scopes}")
            console.log(f"NanoAOD: {self.nanoAOD_version}")
            if self.friend_config != "" and self.friend_mapping != "{}":
                console.log(f"Friend Config: {self.friend_config}")
                console.log(f"Friend Name: {self.friend_name}")
                console.log(f"Friend Mapping: {self.friend_mapping}")
            elif self.friend_mapping != "{}" and self.friend_config == "":
                for key, cfg in self.friend_mapping.items():
                    console.log(f"Friend Config: {key}")
                    console.log(f"Friend Name: {cfg['friend_name']}")
                    console.log(f"Friend Mapping: {cfg.get('requires', [])}")
            console.rule("")

        data = self.set_sample_data(self.parse_samplelist(self.sample_list))
        self.silent = True

        requirements = {}
        if self.friend_config != "" and self.friend_mapping != "{}":
            for samplenick in data["details"]:
                requirements[f"CROWNFriend_{samplenick}_{self.friend_config}"] = (
                    CROWNFriend.req(
                        self,
                        nick=samplenick,
                        all_eras=data["eras"],
                        all_sample_types=data["sample_types"],
                        era=data["details"][samplenick]["era"],
                        sample_type=data["details"][samplenick]["sample_type"],
                        friend_mapping=self.friend_mapping,
                    )
                )
        elif self.friend_mapping != "{}" and self.friend_config == "":
            for samplenick in data["details"]:
                for friend_config in self.friend_mapping.keys():
                    requirements[f"CROWNFriend_{samplenick}_{friend_config}"] = (
                        CROWNFriend.req(
                            self,
                            nick=samplenick,
                            all_eras=data["eras"],
                            all_sample_types=data["sample_types"],
                            era=data["details"][samplenick]["era"],
                            sample_type=data["details"][samplenick]["sample_type"],
                            friend_config=friend_config,
                            friend_mapping=self.friend_mapping,
                        )
                    )
        else:
            for samplenick in data["details"]:
                requirements[f"CROWNRun_{samplenick}"] = CROWNRun.req(
                    self,
                    nick=samplenick,
                    all_eras=data["eras"],
                    all_sample_types=data["sample_types"],
                    era=data["details"][samplenick]["era"],
                    sample_type=data["details"][samplenick]["sample_type"],
                )

        return requirements
