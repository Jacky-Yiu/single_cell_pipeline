'''
Created on Feb 22, 2018

@author: dgrewal
'''

import os
import pypeliner
import pypeliner.managed as mgd
from workflows import germline
from single_cell.utils import helpers
import single_cell

def germline_calling_workflow(workflow, args):

    config = helpers.load_config(args)
    config = config['germline_calling']

    baseimage = config['docker']['single_cell_pipeline']

    basedocker = {'docker_image': config['docker']['single_cell_pipeline']}
    vcftoolsdocker = {'docker_image': config['docker']['vcftools']}
    samtoolsdocker = {'docker_image': config['docker']['samtools']}
    snpeffdocker = {'docker_image': config['docker']['snpeff']}

    bam_files, _ = helpers.get_bams(args['input_yaml'])

    normal_bam_template = args["input_template"]
    normal_bai_template = args["input_template"] + ".bai"

    if "{reads}" in normal_bam_template:
        raise ValueError("input template for germline calling only support region based splits")

    varcalls_dir = os.path.join(
        args['out_dir'], 'results', 'germline_calling')

    samtools_germline_vcf = os.path.join(varcalls_dir, 'raw', 'samtools_germline.vcf.gz')
    snpeff_vcf_filename = os.path.join(varcalls_dir, 'snpeff.vcf')
    normal_genotype_filename = os.path.join(varcalls_dir, 'raw', 'normal_genotype.h5')
    mappability_filename = os.path.join(varcalls_dir, 'raw', 'mappability.h5')
    counts_template = os.path.join(varcalls_dir, 'counts', 'raw', 'counts.h5')
    germline_h5_filename = os.path.join(varcalls_dir, 'germline.h5')

    workflow.setobj(
        obj=mgd.OutputChunks('cell_id'),
        value=bam_files.keys(),
    )
 
    workflow.transform(
        name="get_regions",
        ctx={'mem_retry_increment': 2, 'ncpus': 1, 'mem': config["memory"]['low'], 'docker_image': baseimage},
        func="single_cell.utils.pysamutils.get_regions_from_reference",
        ret=pypeliner.managed.OutputChunks('region'),
        args=(
            config["ref_genome"],
            config["split_size"],
            config["chromosomes"],
        )
    )

    workflow.subworkflow(
        name='samtools_germline',
        func=germline.create_samtools_germline_workflow,
        args=(
            mgd.InputFile("normal.split.bam", "region", template=normal_bam_template),
            mgd.InputFile("normal.split.bam.bai", "region", template=normal_bai_template),
            config['ref_genome'],
            mgd.OutputFile(samtools_germline_vcf, extensions=['.tbi']),
            config,
        ),
        kwargs={'vcftools_docker': vcftoolsdocker,
                'samtools_docker': samtoolsdocker,}
    )

    workflow.subworkflow(
        name='annotate_mappability',
        func="biowrappers.components.variant_calling.mappability.create_vcf_mappability_annotation_workflow",
        args=(
            config['databases']['mappability']['local_path'],
            mgd.InputFile(samtools_germline_vcf, extensions=['.tbi']),
            mgd.OutputFile(mappability_filename),
        ),
        kwargs={'base_docker': basedocker,
                'chromosomes': config['chromosomes']}
    )

    workflow.transform(
        name='annotate_genotype',
        func="single_cell.workflows.germline.tasks.annotate_normal_genotype",
        ctx={'mem_retry_increment': 2, 'ncpus': 1, 'mem': config["memory"]['low']},
        args=(
            mgd.InputFile(samtools_germline_vcf, extensions=['.tbi']),
            mgd.OutputFile(normal_genotype_filename),
            config["chromosomes"],
        ),
    )

    workflow.subworkflow(
        name='snpeff',
        func="biowrappers.components.variant_calling.snpeff.create_snpeff_annotation_workflow",
        args=(
            config['databases']['snpeff']['db'],
            mgd.InputFile(samtools_germline_vcf, extensions=['.tbi']),
            mgd.OutputFile(snpeff_vcf_filename),
        ),
        kwargs={
            'hdf5_output': False,
            'base_docker': basedocker,
            'vcftools_docker': vcftoolsdocker,
            'snpeff_docker': snpeffdocker,
        }
    )

    workflow.subworkflow(
        name='read_counts',
        func="single_cell.variant_calling.create_snv_allele_counts_for_vcf_targets_workflow",
        args=(
            mgd.InputFile('tumour.bam', 'cell_id', fnames=bam_files, extensions=['.bai']),
            mgd.InputFile(samtools_germline_vcf, extensions=['.tbi']),
            mgd.OutputFile(counts_template),
            config['memory'],
        ),
        kwargs={
            'table_name': '/germline_allele_counts',
        },
    )

    workflow.transform(
        name='build_results_file',
        func="biowrappers.components.io.hdf5.tasks.concatenate_tables",
        ctx={'mem_retry_increment': 2, 'ncpus': 1, 'mem': config["memory"]['low'], 'docker_image': baseimage},
        args=([
                mgd.InputFile(counts_template),
                mgd.InputFile(mappability_filename),
                mgd.InputFile(normal_genotype_filename),
            ],
            pypeliner.managed.OutputFile(germline_h5_filename),
        ),
        kwargs={
            'drop_duplicates': True,
        }
    )

    info_file = os.path.join(args["out_dir"],'results', 'germline_calling', "info.yaml")

    results = {
        'germline_data': helpers.format_file_yaml(germline_h5_filename),
    }

    input_datasets = {k: helpers.format_file_yaml(v) for k,v in bam_files.iteritems()}

    metadata = {
        'germline_calling': {
            'version': single_cell.__version__,
            'results': results,
            'containers': config['docker'],
            'input_datasets': input_datasets,
            'output_datasets': None
        }
    }

    workflow.transform(
        name='generate_meta_yaml',
        ctx={'mem_retry_increment': 2, 'ncpus': 1, 'mem': config["memory"]['low'], 'docker_image': baseimage},
        func="single_cell.utils.helpers.write_to_yaml",
        args=(
            mgd.OutputFile(info_file),
            metadata
        )
    )

    return workflow

