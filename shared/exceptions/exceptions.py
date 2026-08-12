class AppException(Exception):
   status_code:int=400
   def __init__(self, message:str):
       self.message=message
       super().__init__(message)

class NotFoundException(AppException):
    status_code=404


class UnauthorizedException(AppException):
    status_code=401


class ValidationException(AppException):
    status_code=422

class ForbiddenException(AppException):
    status_code=403

class ConflictException(AppException):
    status_code=409
    
class PayloadTooLargeException(AppException):
    status_code = 413
