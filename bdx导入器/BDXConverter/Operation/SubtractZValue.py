from ..General.GeneralClass import GeneralClass


class SubtractZValue(GeneralClass):
    def __init__(self) -> None:
        super().__init__()
        self.operationName: str = 'SubtractZValue'
        self.operationNumber: int = 19
