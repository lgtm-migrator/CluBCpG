import pysam
import argparse
import copy
import pandas as pd
import numpy as np


class BamFileReadParser():

    def __init__(self, bamfile, quality_score, read1_5=None, read1_3=None, read2_5=None, read2_3=None):
        self.mapping_quality = quality_score
        self.bamfile = bamfile
        self.read1_5 = read1_5
        self.read1_3 = read1_3
        self.read2_5 = read2_5
        self.read2_3 = read2_3

        if read1_5 or read2_5 or read1_3 or read2_3:
            self.mbias_filtering = True
        else:
            self.mbias_filtering = False

        self.OpenBamFile = pysam.AlignmentFile(bamfile, 'rb')

    # Take an AlignmentSegment extract the XM tag, and return the values
    def get_metylation_tags(self, read):
        tags = read.get_tags()
        for tag in tags:
            if tag[0] == 'XM':
                return tag[1]

    # Take a list of tags and positions, return tuples consisting of (position, tag)
    def merge_pos_tags(self, tags, positions, start_pos, stop_pos):
        output = []
        for pos, status in list(zip(positions, tags)):
            if pos >= start_pos and pos <= stop_pos:
                output.append((pos,status))

        return output

    # Take a list of tuples (pos, tag) and reduce it to only CpG sites
    def extract_cpgs(self, pos_tags):
        read_cpgs = []
        for item in pos_tags:
            if item[1] is 'Z' or item[1] is 'z':
                read_cpgs.append(item)

        return read_cpgs

    # Get reads from the bam file, extract methylation state
    def parse_reads(self, chromosome, start, stop):
        reads = []
        for read in self.OpenBamFile.fetch(chromosome, start, stop):
            if read.mapping_quality >= self.mapping_quality:
                reads.append(read)

        read_cpgs = []

        for read in reads:
            if read.mapping_quality >= 20:
                reduced_read = []
                # Join EVERY XM tag with its aligned_pair location
                for pair, tag in zip(read.get_aligned_pairs(), read.get_tag('XM')):
                    if pair[1]:
                        if read.flag == 83 or read.flag == 163:
                            reduced_read.append((pair[1] - 1, tag))
                        else:
                            reduced_read.append((pair[1], tag))
                    else:
                        continue

                # if mbias was set slice the joined list
                if self.mbias_filtering:
                    if read.is_read1:
                        mbias_5_prime = self.read1_5
                        mbias_3_prime = -self.read1_3
                        if mbias_3_prime == 0:
                            mbias_3_prime = None
                        reduced_read = reduced_read[mbias_5_prime:mbias_3_prime]
                    if read.is_read2:
                        mbias_5_prime = self.read2_5
                        mbias_3_prime = -self.read2_3
                        if mbias_3_prime == 0:
                            mbias_3_prime = None
                        reduced_read = reduced_read[mbias_5_prime:mbias_3_prime]

                read_cpgs.append(reduced_read)

        # Filter the list for positions between start-stop and CpG (Z/z) tags
        output = []
        for read_cpg in read_cpgs:
            temp = []
            for pos, tag in read_cpg:
                if pos and pos >= start and pos <= stop and (tag == 'Z' or tag == 'z'):
                    temp.append((pos, tag))
            output.append(temp)

        return output

    def create_matrix(self, read_cpgs):
        series = []
        for data in read_cpgs:
            positions = []
            statues = []
            for pos, status in data:
                positions.append(pos)
                statues.append(status)
            series.append(pd.Series(statues, positions))

        matrix = pd.concat(series, axis=1)
        matrix = matrix.replace('Z', 1)
        matrix = matrix.replace('z', 0)

        return matrix.T


    def adjust_cpg_positions(self, parsed_reads):
        """Adjust the parse reads output to make all CpG sites on the same base position"""
        lowest = np.inf
        new_output = []
        # Search all reads and find the lowest start site (the C)
        for value in parsed_reads:
            try:
                if value[0][0] < lowest:
                    lowest = value[0][0]
            except IndexError:
                pass
        print(lowest)

        for value in parsed_reads:
            try:
                if value[0][0] != lowest:
                    new_value = []
                    for item in value:
                        loc = item[0] - 1
                        meth_state = item[1]
                        new_value.append((loc, meth_state))
                    new_output.append(new_value)
                else:
                    new_output.append(value)
            except IndexError:
                new_output.append(value)

        return new_output


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("input_bam", help="bam file")
    parser.add_argument("chromosome", help="chromosome to extract from, example: chr19")
    parser.add_argument("end_coordinate", help="Specifcy the final coordinate of the region you wish to extract, example"
                                               " 500 would give you a region randing from bp window_size-500")
    parser.add_argument("-w", "--window", help="Size of the region in bp you with you convert into a matrix",
                        default=200)
    parser.add_argument("-q", "--quality", help="Minimum mapping quality for read to be considered default=20",
                        default=20)

    args = parser.parse_args()

    bam_file = args.input_bam
    quality_score = args.quality
    window_size = args.window
    stop_pos = int(args.end_coordinate)
    chromosome = args.chromosome

    bamfileparser = BamFileReadParser(bam_file, quality_score)

    data = bamfileparser.parse_reads(chromosome, stop_pos-window_size, stop_pos)

    matrix = bamfileparser.create_matrix(data)

    print(matrix)
