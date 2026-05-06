from dataclasses import dataclass


@dataclass
class NfMetaRunnerError(Exception):
    message: str
   
    def __str__(self) -> str:
        return self.message
