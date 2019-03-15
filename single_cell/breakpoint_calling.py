import os
import pypeliner
import pypeliner.managed as mgd
from single_cell.utils import helpers
import single_cell


def breakpoint_calling_workflow(args):

    config = helpers.load_config(args)
    config = config['breakpoint_calling']

    data = helpers.load_pseudowgs_input(args['input_yaml'])
    tumour_cells = data['tumour_cells']
    tumour_cells_id = data['tumour_cells_id']

    normal_bams = data['normal_wgs'] if data['normal_wgs'] else data['normal_cells']
    normal_id = data['normal_wgs_id'] if data['normal_wgs_id'] else data['normal_cells_id']

    calls_dir = os.path.join(
        args['out_dir'], 'results', 'breakpoint_calling'
    )
    raw_data_directory = os.path.join(calls_dir, 'raw')
    breakpoints_filename = os.path.join(calls_dir, 'breakpoints.h5')
    breakpoints_lib_filename = os.path.join(calls_dir, 'breakpoints_lib.h5')
    cell_counts_filename = os.path.join(calls_dir, 'cell_counts.h5')

    ref_data_directory = config['ref_data_directory']

    workflow = pypeliner.workflow.Workflow(ctx={'docker_image': config['docker']['single_cell_pipeline']})

    workflow.setobj(
        obj=mgd.OutputChunks('tumour_cell_id'),
        value=tumour_cells.keys(),
    )

    if isinstance(normal_bams, dict):
        workflow.setobj(
            obj=mgd.OutputChunks('normal_cell_id'),
            value=normal_bams.keys(),
        )
        workflow.set_filenames('normal_cells.bam', 'normal_cell_id', fnames=normal_bams)
        normal_bam = mgd.InputFile('normal_cells.bam', 'normal_cell_id', extensions=['.bai'])
    else:
        normal_bam = mgd.InputFile(normal_bams, extensions=['.bai'])

    if args['destruct']:
        workflow.subworkflow(
            name='destruct',
            ctx={'docker_image': config['docker']['destruct']},
            func="single_cell.workflows.destruct_singlecell.create_destruct_workflow",
            args=(
                normal_bam,
                mgd.InputFile('tumour.bam', 'tumour_cell_id', fnames=tumour_cells),
                config.get('destruct', {}),
                ref_data_directory,
                mgd.OutputFile(breakpoints_filename),
                mgd.OutputFile(breakpoints_lib_filename),
                mgd.OutputFile(cell_counts_filename),
                raw_data_directory,
            ),
        )

    if args['lumpy']:
        varcalls_dir = os.path.join(
            args['out_dir'], 'results', 'breakpoint_calling')
        breakpoints_bed = os.path.join(varcalls_dir, 'lumpy_breakpoints.bed')
        breakpoints_h5 = os.path.join(varcalls_dir, 'lumpy_breakpoints.h5')

        workflow.subworkflow(
            name='lumpy',
            func="single_cell.workflows.lumpy.create_lumpy_workflow",
            args=(
                config,
                mgd.InputFile('tumour.bam', 'tumour_cell_id', fnames=tumour_cells, extensions=['.bai']),
                normal_bam,
                mgd.OutputFile(breakpoints_bed),
                mgd.OutputFile(breakpoints_h5),
            ),
            kwargs={'tumour_id': tumour_cells_id,'normal_id': normal_id}
        )

    info_file = os.path.join(args["out_dir"],'results','breakpoint_calling', "info.yaml")

    results = {
        'destruct_data': helpers.format_file_yaml(breakpoints_filename),
    }

    tumour_dataset = {k: helpers.format_file_yaml(v) for k,v in tumour_cells.iteritems()}
    if isinstance(normal_bams, dict):
        normal_dataset = {k: helpers.format_file_yaml(v) for k, v in normal_bams.iteritems()}
    else:
        normal_dataset = helpers.format_file_yaml(normal_bams)
    input_datasets = {'normal': normal_dataset,
                      'tumour': tumour_dataset}

    metadata = {
        'breakpoint_calling': {
            'ref_data': ref_data_directory,
            'version': single_cell.__version__,
            'results': results,
            'containers': config['docker'],
            'input_datasets': input_datasets,
            'output_datasets': None
        }
    }

    workflow.transform(
        name='generate_meta_yaml',
        ctx=dict(mem=config['memory']['med'],
                 mem_retry_increment=2, ncpus=1),
        func="single_cell.utils.helpers.write_to_yaml",
        args=(
            mgd.OutputFile(info_file),
            metadata
        )
    )

    return workflow

