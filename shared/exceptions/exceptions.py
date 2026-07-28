class AppException(Exception):
    pass


class NotFoundException(AppException):
    pass


class UnauthorizedException(AppException):
    pass


class ValidationException(AppException):
    pass