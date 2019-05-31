'''
Created on Jul 6, 2017

@author: dgrewal
'''
import os
import pypeliner
import pypeliner.managed as mgd
import single_cell
from single_cell.utils import helpers

def create_alignment_workflow(
        fastq_1_filename,
        fastq_2_filename,
        biobloom_metrics,
        ref_genome,
        config,
        args,
):

    disable_biobloom = args['disable_biobloom']

    baseimage = config['docker']['single_cell_pipeline']

    chromosomes = config["chromosomes"]

    workflow = pypeliner.workflow.Workflow()

    workflow.setobj(
        obj=mgd.OutputChunks('chrom'),
        value=chromosomes,
    )

    workflow.setobj(
        obj=mgd.OutputChunks('cell_id', 'lane'),
        value=fastq_1_filename.keys(),
    )

    workflow.transform(
        name='align_reads',
        ctx={'mem': config['memory']['med'], 'ncpus': 1, 'docker_image': baseimage},
        axes=('cell_id', 'lane',),
        func="single_cell.workflows.align.tasks.align_pe",
        args=(
            mgd.InputFile(
                'fastq_1', 'cell_id', 'lane', fnames=fastq_1_filename),
            mgd.InputFile(
                'fastq_2', 'cell_id', 'lane', fnames=fastq_2_filename),
            mgd.TempOutputFile('biobloom_count_metrics', 'cell_id', 'lane'),
            mgd.TempSpace('alignment_temp', 'cell_id', 'lane'),
            config['docker'],
            config['biobloom_filters'],
            config['ref_type']
        )
    )

    workflow.transform(
        name='merge_biobloom',
        func="single_cell.workflows.align.tasks.merge_biobloom",
        axes=('cell_id',),
        args=( mgd.TempInputFile('biobloom_count_metrics', 'cell_id', 'lane'),
               mgd.TempOutputFile('biobloom_count_metrics_merged', 'cell_id'),
               disable_biobloom,
               mgd.InputInstance('cell_id')
               )
    )


    workflow.transform(
        name='merge_all_biobloom',
        func="single_cell.utils.csvutils.concatenate_csv",
        args=(mgd.TempInputFile('biobloom_count_metrics_merged', 'cell_id'),
              mgd.OutputFile(biobloom_metrics),
              )
    )

    return workflow
