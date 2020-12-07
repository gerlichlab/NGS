"""Tests for flexible pileup"""
import unittest
import pickle
import pandas as pd
import numpy as np
import cooler
from ngs import HiCTools as HT


class TestFlexiblePileupICCF(unittest.TestCase):
    """Tests pileup function that accepts windows of differing size."""

    def test_equal_sized_windows(self):
        """Test flexible pileup with equally sized windows."""
        position_frame = pd.read_csv("testFiles/posPileupSymmetric.csv")
        arms = pd.DataFrame({"chrom": "chrSyn", "start": 0, "end": 4990000}, index=[0])
        cooler_file = cooler.Cooler("testFiles/test2.mcool::/resolutions/10000")
        result = HT.extract_windows_different_sizes_iccf(
            position_frame, arms, cooler_file
        )
        # load expected extracted windows
        with open("testFiles/test_pilesup_symmetric.pickle", "rb") as file_pointer:
            expected = pickle.load(file_pointer)
        self.assertTrue(all(np.allclose(i, j) for i, j in zip(result, expected)))

    def test_equal_sized_windows_different_arms(self):
        """tests pileup on same sized windows that are on different chromosomal
        arms."""
        position_frame = pd.read_csv("testFiles/posPileupSymmetric.csv")
        arms = pd.DataFrame(
            {
                "chrom": ["chrSyn", "chrSyn"],
                "start": [0, 250000],
                "end": [250000, 4990000],
            }
        )
        cooler_file = cooler.Cooler("testFiles/test2.mcool::/resolutions/10000")
        result = HT.extract_windows_different_sizes_iccf(
            position_frame, arms, cooler_file
        )
        # load expected extracted windows
        with open("testFiles/test_pilesup_symmetric.pickle", "rb") as file_pointer:
            expected = pickle.load(file_pointer)
        self.assertTrue(all(np.allclose(i, j) for i, j in zip(result, expected)))

    def test_differently_sized_windows(self):
        """Test flexible pileup with equally sized windows."""
        position_frame = pd.read_csv("testFiles/posPileupAsymmetric.csv")
        arms = pd.DataFrame({"chrom": "chrSyn", "start": 0, "end": 4990000}, index=[0])
        cooler_file = cooler.Cooler("testFiles/test3.mcool::/resolutions/10000")
        result = HT.extract_windows_different_sizes_iccf(
            position_frame, arms, cooler_file
        )
        # load expected extracted windows
        with open("testFiles/test_pilesup_asymmetric.pickle", "rb") as file_pointer:
            expected = pickle.load(file_pointer)
        self.assertTrue(all(np.allclose(i, j) for i, j in zip(result, expected)))

    def test_differently_sized_windows_different_arms(self):
        """tests pileup on differently sized windows that are on different chromosomal
        arms."""
        position_frame = pd.read_csv("testFiles/posPileupAsymmetric.csv")
        arms = pd.DataFrame(
            {
                "chrom": ["chrSyn", "chrSyn"],
                "start": [0, 250000],
                "end": [250000, 4990000],
            }
        )
        cooler_file = cooler.Cooler("testFiles/test3.mcool::/resolutions/10000")
        result = HT.extract_windows_different_sizes_iccf(
            position_frame, arms, cooler_file
        )
        # load expected extracted windows
        with open("testFiles/test_pilesup_asymmetric.pickle", "rb") as file_pointer:
            expected = pickle.load(file_pointer)
        self.assertTrue(all(np.allclose(i, j) for i, j in zip(result, expected)))


class TestFlexiblePileupObsExp(unittest.TestCase):
    """Tests pileup function that accepts windows of differing size."""

    def test_equal_sized_windows(self):
        """Test flexible pileup with equally sized windows (obs/exp)."""
        position_frame = pd.read_csv("testFiles/posPileupSymmetric.csv")
        arms = pd.DataFrame({"chrom": "chrSyn", "start": 0, "end": 4990000}, index=[0])
        cooler_file = cooler.Cooler("testFiles/test2.mcool::/resolutions/10000")
        expected = HT.get_expected(cooler_file, arms, proc=2, ignore_diagonals=0)
        result = HT.extract_windows_different_sizes_obs_exp(
            position_frame, arms, cooler_file, expected
        )
        # load expected extracted windows
        with open(
            "testFiles/test_pilesup_symmetric_obs_exp.pickle", "rb"
        ) as file_pointer:
            expected = pickle.load(file_pointer)
        self.assertTrue(all(np.allclose(i, j) for i, j in zip(result, expected)))

    def test_differently_sized_windows(self):
        """Test flexible pileup with differently sized windows (obs/exp)."""
        position_frame = pd.read_csv("testFiles/posPileupAsymmetric.csv")
        arms = pd.DataFrame({"chrom": "chrSyn", "start": 0, "end": 4990000}, index=[0])
        cooler_file = cooler.Cooler("testFiles/test3.mcool::/resolutions/10000")
        expected = HT.get_expected(cooler_file, arms, proc=2, ignore_diagonals=0)
        result = HT.extract_windows_different_sizes_obs_exp(
            position_frame, arms, cooler_file, expected
        )
        # load expected extracted windows
        with open(
            "testFiles/test_pilesup_asymmetric_obs_exp.pickle", "rb"
        ) as file_pointer:
            expected = pickle.load(file_pointer)
        self.assertTrue(all(np.allclose(i, j) for i, j in zip(result, expected)))


if __name__ == "__main__":
    res = unittest.main(verbosity=3, exit=False)
