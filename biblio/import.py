# coding=utf-8
import sys
sys.path.append("..")
from kuha import importer
args = sys.argv + ["biblio.ini"]
importer.main(args)