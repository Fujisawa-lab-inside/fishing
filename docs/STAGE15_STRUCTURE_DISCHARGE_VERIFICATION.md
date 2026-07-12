# Stage 15 hydraulic structure discharge verification

## Scope

This stage implements generic，isolated hydraulic structure laws without selecting actual Onga River coefficients or operating data．The module is not connected to the public simulator．

## Supported modes

- `disabled`
- signed `fixed_discharge`
- bidirectional `head_orifice`
- `gate_orifice` with width，maximum opening，and opening fraction

Positive discharge is defined from cell A to cell B．Head-driven discharge reverses automatically when the head difference changes sign．No permanent river-axis direction is assigned．

## Conservative transfer

Each structure transfer produces equal and opposite mass sources in its two adjacent cells．Optional directional momentum transport also produces equal and opposite momentum sources．Multiple structures can be accumulated while retaining global conservation．

## Synthetic verification

1．The orifice equation matches its analytical value．
2．Reversing the head difference reverses discharge sign．
3．Equal heads and zero opening produce zero discharge．
4．Gate discharge scales linearly with opening area for a fixed head difference．
5．Time-dependent fixed discharge and gate opening are evaluated at the requested time．
6．Positive and reverse transfers conserve mass and momentum．
7．Multiple transfers conserve globally．
8．Invalid opening，negative coefficients，and unsupported modes are rejected．

## Safeguards

No discharge coefficient，effective area，gate opening，fishway flow，head series，or momentum closure is approved for the real site by this stage．The approved 679,791-pixel water domain，legacy flow model，and public display remain unchanged．
