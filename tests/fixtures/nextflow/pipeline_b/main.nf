// Second fixture pipeline: different script, so its tasks never share hashes with pipeline_a.
params.counter = null
params.outdir  = 'out_b'

process B_ONE {
    publishDir params.outdir, mode: 'copy'

    input:
    val x

    output:
    path "b_one_${x}.txt"

    script:
    """
    echo "b_one:${x}" >> ${params.counter}
    echo ${x} > b_one_${x}.txt
    """
}

workflow {
    B_ONE(Channel.of(1, 2))
}
