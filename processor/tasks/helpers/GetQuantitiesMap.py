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
    args = parser.parse_args()
    return args


def read_quantities_map(input_file, era, sample_type, scope, outputfile):
    print(f"Reading quantities Map from {input_file}")
    data = {}
    ROOT.gSystem.Load(os.path.abspath(__file__), "/maplib.so")
    f = ROOT.TFile.Open(input_file)
    name = "shift_quantities_map"
    m = f.Get(name)
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
    read_quantities_map(args.input, args.era, args.sample_type, args.scope, args.output)
    print("Done")
    exit(0)
