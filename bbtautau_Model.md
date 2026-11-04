# UHH bbtautau Model


**Neutrino regression**: Regresses the missing neutrino 3-momenta per tau decay. In case of leptonic decays, the predicted momentum corresponds to the sum of the two neutrinos produced in the decay. No k-fold cross validation was used as the training data is based on the Run 2 resonant analysis. Internally, the provided network is an ensemble of five trainings.

## Location

- Regression: `/afs/cern.ch/work/m/mrieger/public/hbt/for_kit/models/nu_regression.tgz`

## Loading model

All archives contain a model directory, which can be loaded with standard TensorFlow.

```python
import numpy as np
import tensorflow as tf

model = tf.saved_model.load(model_dir)

# continuous inputs, tf.float32
# categorical inputs, tf.int32
output = model([continuous_inputs, categorical_inputs], training=False)
```

## Input features

The sets of input features are identical between both types of models, and input normalization is done internally.
Input features are divided into continuous and categorical features.
As plain 2D tensors are used as inputs, the order in which they are provided is important and must match the order defined in the lists below.

**Note 1**: Take note of the rotation to the di-lepton system for some four-vectors, as well as for the output of the regression, which have to be done manually.
See the corresponding section below.

**Note 2**: `bjet1` and `bjet2` correspond to two jets selected by the HHB-tagger to stem most likely from the decay of a Higgs boson.
The outputs of this tagger are ordered and thus, define what is considered `bjet1` and `bjet2`, respectively.

### Continuous

- `met_px` (*): MET px.
- `met_py` (*): MET py.
- `met_cov00`: MET covariance matrix element (0,0).
- `met_cov01`: MET covariance matrix element (0,1).
- `met_cov11`: MET covariance matrix element (1,1).
- `lep1_px` (*): Lepton 1 px (visible).
- `lep1_py` (*): Lepton 1 py (visible).
- `lep1_pz`: Lepton 1 pz (visible).
- `lep1_e`: Lepton 1 energy (visible).
- `lep2_px` (*): Lepton 2 px (visible).
- `lep2_py` (*): Lepton 2 py (visible).
- `lep2_pz`: Lepton 2 pz (visible).
- `lep2_e`: Lepton 2 energy (visible).
- `bjet1_px` (*): B-jet 1 px.
- `bjet1_py` (*): B-jet 1 py.
- `bjet1_pz`: B-jet 1 pz.
- `bjet1_e`: B-jet 1 energy.
- `bjet1_tag_b`: B-jet 1 `B` score.
- `bjet1_tag_cvsb`: B-jet 1 `CvB` score.
- `bjet1_tag_cvsl`: B-jet 1 `CvL` score.
- `bjet1_hhbtag`: B-jet 1 HHB-tagger score.
- `bjet2_px` (*): B-jet 2 px.
- `bjet2_py` (*): B-jet 2 py.
- `bjet2_pz`: B-jet 2 pz.
- `bjet2_e`: B-jet 2 energy.
- `bjet2_tag_b`: B-jet 2 `B` score.
- `bjet2_tag_cvsb`: B-jet 2 `CvB` score.
- `bjet2_tag_cvsl`: B-jet 2 `CvL` score.
- `bjet2_hhbtag`: B-jet 2 HHB-tagger score.
- `fatjet_px` (*): Fatjet px.
- `fatjet_py` (*): Fatjet py.
- `fatjet_pz`: Fatjet pz.
- `fatjet_e`: Fatjet energy.
- `htt_e`: Di-tau system energy (visible).
- `htt_px` (*): Di-tau system px (visible).
- `htt_py` (*): Di-tau system py (visible).
- `htt_pz`: Di-tau system pz (visible).
- `hbb_e`: Di-b-jet system energy.
- `hbb_px` (*): Di-b-jet system px.
- `hbb_py` (*): Di-b-jet system py.
- `hbb_pz`: Di-b-jet system pz.
- `htthbb_e`: Combined di-tau and di-b-jet system energy.
- `htthbb_px` (*): Combined di-tau and di-b-jet system px.
- `htthbb_py` (*): Combined di-tau and di-b-jet system py.
- `htthbb_pz`: Combined di-tau and di-b-jet system pz.
- `httfatjet_e`: Combined di-tau and fatjet system energy.
- `httfatjet_px` (*): Combined di-tau and fatjet system px.
- `httfatjet_py` (*): Combined di-tau and fatjet system py.
- `httfatjet_pz`: Combined di-tau and fatjet system pz.

(*) Feature depends on phi-rotation.

### Categorical

- `channel`: 0: mutau, 1: etau, 2: tautau
- `dm1`: Decay mode of first lepton. e/mu: -1, tau: 0,1,10,11
- `dm2`: Decay mode of second lepton (always tau). 0,1,10,11
- `charge1`: Charge of first lepton.
- `charge2`: Charge of second lepton.
- `is_boosted`: Whether the event contains a fatjet. If your selection does not consider fatjets, pass `0`.
- `has_bjet_pair`: Whether the event contains a pair of b-jets. If your selection always requires two AK4 jets, pass `1`.

### Rotation to di-lepton system

To canonicalize the (mostly) arbitrary azimuthal orientation of events, we decided to rotate all objects such that the di-lepton system has a phi value of 0.

The rotation is rather trivial and can be performed as follows.

```python
# generic rotation helper
def rotate(px, py, ref_phi):
    new_phi = np.arctan2(py, px, dtype=np.float64) + ref_phi
    pt = (px**2 + py**2)**0.5
    return pt * np.cos(new_phi), pt * np.sin(new_phi)

# compute di-lep phi as reference
dilep_phi = np.arctan2(lep1.py + lep2.py, lep1.px + lep2.px, dtype=np.float64)

# rotate met
met_px, met_py = rotate(met_px, met_py, -dilep_phi)  # note the negative sign
```

Likewise, neutrino momenta produced by the regression need to be rotated back into the detector system.

```python
nu_px, nu_py = rotate(nu_px, nu_py, dilep_phi)  # note the positive sign
```
