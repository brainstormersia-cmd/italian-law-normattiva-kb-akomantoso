class NormattivaError(Exception):
    pass


class IngestionError(NormattivaError):
    pass


class ParsingError(NormattivaError):
    pass


class ValidationError(NormattivaError):
    pass
