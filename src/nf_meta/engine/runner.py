import logging
from enum import StrEnum

from src.nf_meta.engine.graph import MetaworkflowGraph

logger = logging.getLogger()

class Runners(StrEnum):
    PYTHON = "python"
    DAISY_CHAIN = "daisy_chain"
    NEXTFLOW_MONO = "nextflow_mono"


# ToDO: Receive a Metawf_graph
def run(g: MetaworkflowGraph, runner: Runners) -> None:
    logger.info("Started runner")


# TODO: Implement with protocols
