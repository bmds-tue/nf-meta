// Fixture for tests/integration: each executed (non-cached) task appends a line
// to params.counter, so cache hits are visible as "no new line".
params.counter = null
params.input   = null
params.outdir  = 'out_a'
// Failure switches for resume-after-failure tests (A_TWO only).
params.fail_two     = false
params.min_cpus_two = 1

process A_ONE {
    publishDir params.outdir, mode: 'copy'

    input:
    val x

    output:
    path "a_one_${x}.txt"

    script:
    """
    echo "a_one:${x}" >> ${params.counter}
    echo ${x} > a_one_${x}.txt
    """

    stub:
    """
    echo "a_one_stub:${x}" >> ${params.counter}
    touch a_one_${x}.txt
    """
}

process A_TWO {
    input:
    path files

    output:
    path "a_two.txt"

    script:
    """
    echo "a_two" >> ${params.counter}
    ${params.fail_two.toString() == 'true' ? 'exit 1' : ''}
    [ ${task.cpus} -ge ${params.min_cpus_two} ] || exit 1
    cat ${files} > a_two.txt
    """
}

workflow {
    if (params.input) {
        println "INPUT_RESOLVED=${file(params.input).toAbsolutePath()}"
        println "INPUT_EXISTS=${file(params.input).exists()}"
    }
    A_ONE(Channel.of(1, 2)) | collect | A_TWO
}
