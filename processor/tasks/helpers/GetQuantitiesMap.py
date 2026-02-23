import ROOT
import argparse
import json
import os


def parse_args():
    parser = argparse.ArgumentParser(description="Readout Quantities Map")
    parser.add_argument("--input", help="input file")
    parser.add_argument("--era", help="era")
    parser.add_argument("--sample_type", help="sample_type")
    parser.add_argument("--scope", help="scope")
    parser.add_argument("--output", help="output file")
    parser.add_argument("--libdir", help="dict parsing library")
    args = parser.parse_args()
    return args


def read_quantities_map(input_file, era, sample_type, scope, outputfile, libdir):
    print(f"Reading quantities Map from {input_file}")

    # Load dict parsing lib
    lib_path = os.path.abspath(os.path.join(libdir, "libMyDicts.so"))
    # Physical file check
    if not os.path.exists(lib_path):
        raise FileNotFoundError(f"Missing library: {lib_path}")
    # Evaluate ROOT-specific return codes
    result = ROOT.gSystem.Load(lib_path)
    if result < 0:
        err_type = (
            "Version mismatch" if result == -2 else "Linker error/Missing dependency"
        )
        raise ImportError(f"Load failed ({result}): {err_type} for {lib_path}")

    f = ROOT.TFile.Open(input_file)
    name = "shift_quantities_map"
    m = f.Get(name)
    data = {}
    for shift, quantities in m:
        data[str(shift)] = sorted([str(quantity) for quantity in quantities])
    f.Close()
    print(f"Successfully read quantities map from {input_file}")
    output = {}
    output[era] = {}
    output[era][sample_type] = {}
    output[era][sample_type][scope] = data
    with open(outputfile, "w") as f:
        json.dump(output, f, indent=4)


# call the function with the input file
if __name__ == "__main__":
    args = parse_args()
    read_quantities_map(
        args.input, args.era, args.sample_type, args.scope, args.output, args.libdir
    )
    print("Done")
    exit(0)
