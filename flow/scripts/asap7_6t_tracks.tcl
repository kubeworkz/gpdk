# Track definitions for the ASAP7 6T library (0.216 um rows).
# Same upper-layer grid as ORFS's asap7 make_tracks.tcl; M2 is re-spaced for
# the 6T row.  M2 has six 0.036 um tracks at 0.036, 0.072, 0.108, 0.144,
# 0.180 and 0.216 um, with the same 0.009 um x offset.
make_tracks Pad -x_offset 0.116 -x_pitch 0.080 -y_offset 0.116 -y_pitch 0.080
make_tracks M9 -x_offset 0.116 -x_pitch 0.080 -y_offset 0.116 -y_pitch 0.080
make_tracks M8 -x_offset 0.116 -x_pitch 0.080 -y_offset 0.116 -y_pitch 0.080
make_tracks M7 -x_offset 0.016 -x_pitch 0.064 -y_offset 0.016 -y_pitch 0.064
make_tracks M6 -x_offset 0.012 -x_pitch 0.048 -y_offset 0.016 -y_pitch 0.064
make_tracks M5 -x_offset 0.012 -x_pitch 0.048 -y_offset 0.012 -y_pitch 0.048
make_tracks M4 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.012 -y_pitch 0.048
make_tracks M3 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.009 -y_pitch 0.036

make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.036 -y_pitch 0.216
make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.072 -y_pitch 0.216
make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.108 -y_pitch 0.216
make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.144 -y_pitch 0.216
make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.180 -y_pitch 0.216
make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.216 -y_pitch 0.216

make_tracks M1 -x_offset 0.0 -x_pitch 0.036 -y_offset 0.0 -y_pitch 0.036
