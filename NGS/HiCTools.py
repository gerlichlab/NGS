"""A collections of functions to facilitate
analysis of HiC data based on the cooler and cooltools
interfaces."""
import multiprocess
import cooltools.expected
import cooltools.snipping
import pandas as pd
import bioframe
import cooler
import warnings
import pairtools
from typing import Tuple, Dict, Callable
import numpy as np


# define type aliases

cisTransPairs = Dict[str, pd.DataFrame]
pairsSamples = Dict[str, cisTransPairs]

# define functions


def getExpected(clr: cooler.Cooler, arms: pd.DataFrame,
                proc: int = 20, ignoreDiagonals: int = 2) -> pd.DataFrame:
    """Takes a clr file handle and a pandas dataframe
    with chromosomal arms (generated by getArmsHg19()) and calculates
    the expected read number at a certain genomic distance.
    The proc parameters defines how many processes should be used
    to do the calculations. ingore_diags specifies how many diagonals
    to ignore (0 mains the main diagonal, 1 means the main diagonal
    and the flanking tow diagonals and so on)"""
    with multiprocess.Pool(proc) as pool:
        expected = cooltools.expected.diagsum(
            clr,
            list(arms.itertuples(index=False, name=None)),
            transforms={
                'balanced': lambda p: p['count'] * p['weight1'] * p['weight2']
            },
            map=pool.map, ignore_diags=ignoreDiagonals
        )
    # construct a single dataframe for all regions (arms)
    expected_df = pd.concat([exp.reset_index().assign(chrom=reg[0], start=reg[1], end=reg[2])
                             for reg, exp in expected.items()])
    # aggregate diagonals over the regions specified by chrom, start, end (arms)
    expected_df = expected_df.groupby(['chrom', 'start', 'end', 'diag']).aggregate({
        'n_valid': 'sum',
        'count.sum': 'sum',
        'balanced.sum': 'sum'}).reset_index()
    # account for different number of valid bins in diagonals
    expected_df['balanced.avg'] = expected_df['balanced.sum'] / \
        expected_df['n_valid']
    return expected_df


def getArmsHg19() -> pd.DataFrame:
    """Downloads the coordinates for chromosomal arms of the
    genome assembly hg19 and returns it as a dataframe."""
    # download chromosomal sizes
    chromsizes = bioframe.fetch_chromsizes('hg19')
    # download centromers
    cens = bioframe.fetch_centromeres('hg19')
    cens.set_index('chrom', inplace=True)
    cens = cens.mid
    # define chromosomes that are well defined (filter out unassigned contigs)
    GOOD_CHROMS = list(chromsizes.index[:23])
    # construct arm regions (for each chromosome fro 0-centromere and from centromere to the end)
    arms = [arm for chrom in GOOD_CHROMS for arm in ((chrom, 0, cens.get(
        chrom, 0)), (chrom, cens.get(chrom, 0), chromsizes.get(chrom, 0)))]
    # construct dataframe out of arms
    arms = pd.DataFrame(arms, columns=['chrom', 'start', 'end'])
    return arms


def assignRegions(window: int, binsize: int, chroms: pd.Series,
                  positions: pd.Series, arms: pd.DataFrame) -> pd.DataFrame:
    """Constructs a 2d region around a series of chromosomal location.
    Window specifies the windowsize for the constructed regions. The total region
    assigned will be pos-window until pos+window. The binsize specifies the size
    of the HiC bins. The positions which represent the center of the regions
    is givin the the chroms series and the positions series."""
    # construct windows from the passed chromosomes and positions
    snipping_windows = cooltools.snipping.make_bin_aligned_windows(
        binsize,
        chroms.values,
        positions.values,
        window
    )
    # assign chromosomal arm to each position
    snipping_windows = cooltools.snipping.assign_regions(
        snipping_windows,
        list(arms.itertuples(index=False, name=None)))
    return snipping_windows


def assignRegions2d(window: int, binsize: int, chroms1: pd.Series,
                    positions1: pd.Series, chroms2: pd.Series,
                    positions2: pd.Series, arms: pd.DataFrame) -> pd.DataFrame:
    """Constructs a 2d region around a series of chromosomal location pairs.
    Window specifies the windowsize for the constructed regions. The total region
    assigned will be pos-window until pos+window. The binsize specifies the size
    of the HiC bins. The positions which represent the center of the regions
    is given by  the chroms1 and chroms2 series as well as the
    positions1 and positions2 sereis."""
    # construct windows from the passed chromosomes 1 and positions 1
    windows1 = assignRegions(window, binsize, chroms1, positions1, arms)
    windows1.columns = [str(i) + "1" for i in windows1.columns]
    # construct windows from the passed chromosomes 1 and positions 1
    windows2 = assignRegions(window, binsize, chroms2, positions2, arms)
    windows2.columns = [str(i) + "2" for i in windows2.columns]
    windows = pd.concat((windows1, windows2), axis=1)
    # concatenate windows
    windows = pd.concat((windows1, windows2), axis=1)
    # filter for mapping to different regions
    windowsFinal = windows.loc[windows["region1"] == windows["region2"], :]
    # subset data and rename regions
    windowsSmall = windowsFinal[["chrom1", "start1", "end1", "chrom2", "start2", "end2", "region1"]]
    windowsSmall.columns = ["chrom1", "start1", "end1", "chrom2", "start2", "end2", "region"]
    return windowsSmall


def doPileupObsExp(clr: cooler.Cooler, expected_df: pd.DataFrame,
                   snipping_windows: pd.DataFrame, proc: int = 5,
                   collapse: bool = True) -> np.ndarray:
    """Takes a cooler file handle, an expected dataframe
    constructed by getExpected, snipping windows constructed
    by assignRegions and performs a pileup on all these regions
    based on the obs/exp value. Returns a numpy array
    that contains averages of all selected regions.
    The collapse parameter specifies whether to return
    the average window over all piles (collapse=True), or the individual
    windows (collapse=False)."""
    oe_snipper = cooltools.snipping.ObsExpSnipper(clr, expected_df)
    # set warnings filter to ignore RuntimeWarnings since cooltools
    # does not check whether there are inf or 0 values in
    # the expected dataframe
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with multiprocess.Pool(proc) as pool:
            # extract a matrix of obs/exp avlues for each snipping_window
            oe_pile = cooltools.snipping.pileup(
                snipping_windows,
                oe_snipper.select, oe_snipper.snip,
                map=pool.map)
    if collapse:
        # calculate the average of all windows
        collapsed_pile = np.nanmean(
            oe_pile[:, :, :], axis=2
        )
        return collapsed_pile
    else:
        return oe_pile


def doPileupICCF(clr: cooler.Cooler, snipping_windows: pd.DataFrame,
                 proc: int = 5, collapse: bool = True) -> np.ndarray:
    """Takes a cooler file handle and snipping windows constructed
    by assignRegions and performs a pileup on all these regions
    based on the corrected HiC counts. Returns a numpy array
    that contains averages of all selected regions. The collapse
    parameter specifies whether to return
    the average window over all piles (collapse=True), or the individual
    windows (collapse=False)."""
    ICCF_snipper = cooltools.snipping.CoolerSnipper(clr)
    with multiprocess.Pool(proc) as pool:
        ICCF_pile = cooltools.snipping.pileup(
                                            snipping_windows,
                                            ICCF_snipper.select, ICCF_snipper.snip,
                                            map=pool.map)
    if collapse:
        # calculate the average of all windows
        collapsed_pile_plus = np.nanmean(
            ICCF_pile[:, :, :], axis=2
        )
        return collapsed_pile_plus
    else:
        return ICCF_pile


def slidingDiamond(array: np.ndarray, sideLen: int = 6) -> Tuple[np.ndarray, np.ndarray]:
    """Will slide a dimaond of side length 'sideLen'
    down the diagonal of the passed array and return
    the average values for each position and
    the relative position of each value with respect
    to the center of the array (in Bin units)"""
    # initialize accumulators for diamond value and x-position
    diamondAccumulator = list()
    binAccumulator = list()
    halfWindow = sideLen//2
    for i in range(0, (array.shape[0] - halfWindow)):
        # extract diamond
        diamondArray = array[i: (i+halfWindow) + 1, i:(i+halfWindow) + 1]
        # set inf to nan for calculation of mean
        diamondArray[np.isinf(diamondArray)] = np.nan
        diamondAccumulator.append(np.nanmean(diamondArray))
        # append x-value for this particular bin
        binAccumulator.append(np.mean(range(i, (i+halfWindow) + 1,)))
    return (np.array(binAccumulator - np.median(binAccumulator)), np.array(diamondAccumulator))


def loadPairs(path: str) -> pd.DataFrame:
    """Function to load a .pairs or .pairsam file
    into a pandas dataframe.
    This only works for relatively small files!"""
    # TODO Add iterator to load chunks to be able to handle large files
    # get handels for header and pairs_body
    header, pairs_body = pairtools._headerops.get_header(
            pairtools._fileio.auto_open(path, 'r'))
    # extract column names from header
    cols = pairtools._headerops.extract_column_names(header)
    # read data into dataframe
    frame = pd.read_csv(pairs_body, sep="\t", names=cols)
    return frame


def downSamplePairs(sampleDict: pairsSamples, Distance: int = 10**4) -> pairsSamples:
    """Will downsample cis and trans reads in sampleDict to contain
    as many combined cis and trans reads as the sample with the lowest readnumber of the
    specified distance. """
    # initialize output dictionary
    outDict = {sample: {} for sample in sampleDict}
    for sample in sampleDict.keys():
        # create temporary dataframes
        cisTemp = sampleDict[sample]["cis"]
        cisTemp["rType"] = "cis"
        transTemp = sampleDict[sample]["trans"]
        transTemp["rType"] = "trans"
        # concatenate them and store in outdict
        outDict[sample]["all"] = pd.concat((cisTemp, transTemp))
        # filter on distance
        outDict[sample]["all"] = outDict[sample]["all"].loc[(outDict[sample]["all"]["pos2"] - outDict[sample]["all"]["pos1"]) > Distance, :]
    # get the minimum number of reads
    minReads = min([len(i["all"]) for i in outDict.values()])
    # do the downsampling and split into cis and trans
    for sample in outDict.keys():
        outDict[sample]["all"] = outDict[sample]["all"].sample(n=minReads)
        outDict[sample]["cis"] = outDict[sample]["all"].loc[outDict[sample]
                                                            ["all"]["rType"] == "cis", :]
        outDict[sample]["trans"] = outDict[sample]["all"].loc[outDict[sample]
                                                              ["all"]["rType"] == "trans", :]
        # get rid of all reads
        outDict[sample].pop("all")
    return outDict


def pileToFrame(pile: np.ndarray) -> pd.DataFrame:
    """Takes a pile of pileup windows produced
    by doPileupsObsExp/doPileupsICCF (with collapse set to False;
    this is numpy ndarray with the following dimensions:
    pile.shape = [windoSize, windowSize, windowNumber])
    and arranges them as a dataframe with the pixels of the
    pile flattened into columns and each individual window
    being a row.
    Window1: | Pixel 1 | Pixel 2 | Pixel3| ...
    Window2: | Pixel 1 | Pixel 2 | Pixel3| ...
    Window3: | Pixel 1 | Pixel 2 | Pixel3| ...
    """
    return pd.DataFrame(pile.flatten().reshape(pile.shape[0]**2, pile.shape[2])).transpose()


def getPairingScore(clr: cooler.Cooler, windowsize: int = 4 * 10**4,
                    func: Callable = np.mean, regions: pd.DataFrame = pd.DataFrame(),
                    norm: bool = True) -> pd.DataFrame:
    """Takes a cooler file (clr),
    a windowsize (windowsize), a summary
    function (func) and a set of genomic
    regions to calculate the pairing score
    as follows: A square with side-length windowsize
    is created for each of the entries in the supplied genomics
    regions and the summary function applied to the Hi-C pixels
    at the location in the supplied cooler file. The results are
    returned as a dataframe. If no regions are supplied, regions
    are constructed for each bin in the cooler file to
    construct a genome-wide pairing score."""
    # Check whether genomic regions were supplied
    if len(regions) == 0:
        # If no regions are supplied, pregenerate all bins; drop bins with nan weights
        regions = clr.bins()[:].dropna()
        # find midpoint of each bin to assign windows to each midpoint
        regions.loc[:, "mid"] = (regions["start"] + regions["end"])//2
    # drop nan rows from regions
    regions = regions.dropna()
    # fix indices
    regions.index = range(len(regions))
    regions.loc[:, "binID"] = range(len(regions))
    # Chromosomal arms are needed so each process only extracts a subset from the file
    arms = getArmsHg19()
    # extract all windows
    windows = assignRegions(windowsize, clr.binsize, regions["chrom"],
                            regions["mid"], arms)
    # add binID to later merge piles
    windows.loc[:, "binID"] = regions["binID"]
    windows = windows.dropna()
    # generate pileup
    pile = doPileupICCF(clr, windows, collapse=False)
    # convert to dataframe
    pileFrame = pileToFrame(pile)
    # apply function to each row (row = individual window)
    summarized = pileFrame.apply(func, axis=1)
    # subset regions with regions that were assigned windows
    output = pd.merge(regions, windows, on="binID", suffixes=("", "_w")).dropna()
    # add results
    output.loc[:, "PairingScore"] = summarized
    # normalize by median
    if norm:
        output.loc[:, "PairingScore"] = output["PairingScore"] - np.median(output.dropna()["PairingScore"])
    return output[["chrom", "start", "end", "PairingScore"]]

