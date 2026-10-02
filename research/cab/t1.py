from cabprobe import *
emu = emu_open(state='cab.dst')
run(emu, [["press","DOWN"],["wait",20],["shot","d1"],["press","RIGHT"],["wait",40],["shot","d1r"],
          ["press","DOWN"],["wait",20],["press","RIGHT"],["wait",40],["shot","skin1"],
          ["press","DOWN"],["wait",20],["press","RIGHT"],["wait",40],["shot","hair1"],
          ["press","DOWN"],["wait",20],["press","RIGHT"],["wait",40],["shot","hcol1"]], tag='t1')
os._exit(0)
