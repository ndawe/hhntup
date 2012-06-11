#!/bin/bash

grid-submit -u group.phys-higgs -m datasets.cfg -s HHSkim2.py -v 1 mc11_p851_v10_skim \
--antiMatch "*TPileupReweighting.prw.root*" --site SFU-LCG2_LOCALGROUPDISK \
--official --voms=atlas:/atlas/phys-higgs/Role=production