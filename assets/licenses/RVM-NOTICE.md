# Robust Video Matting

Optional local background-removal component: Robust Video Matting, MobileNetV3.
Authors: Shanchuan Lin, Linjie Yang, Imran Saleemi, Soumyadip Sengupta.
Upstream: https://github.com/PeterL1n/RobustVideoMatting
Paper: https://arxiv.org/abs/2108.11515

Official TorchScript weights are downloaded from release **v1.0.0**, not included in Git.
The exact SHA-256 values are pinned in `backend/matting.py` and checked before inference.

Upstream is licensed under GNU GPL v3; the complete license is in
`RVM-GPL-3.0.txt`. Upstream source is available at the repository above.
This notice does not relicense the rest of VietCut. Distribution of a combined
product using this component must comply with the applicable GPL obligations;
using a separate process is not an exemption from them.

PyTorch (BSD-style) and OpenCV (Apache 2.0) are installed as separate dependencies
with their original license files preserved in the isolated environment.
