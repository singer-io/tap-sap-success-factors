class SAPSuccessFactorsError(Exception):
    """Generic API error."""

    def __init__(self, message=None, response=None):
        super().__init__(message)
        self.message = message
        self.response = response


class SAPSuccessFactorsBadRequestError(SAPSuccessFactorsError):
    """400 bad request."""


class SAPSuccessFactorsUnauthorizedError(SAPSuccessFactorsError):
    """401 unauthorized."""


class SAPSuccessFactorsForbiddenError(SAPSuccessFactorsError):
    """403 forbidden."""


class SAPSuccessFactorsNotFoundError(SAPSuccessFactorsError):
    """404 not found."""


class SAPSuccessFactorsRateLimitError(SAPSuccessFactorsError):
    """429 rate limit — honour Retry-After response header."""


class SAPSuccessFactorsServer5xxError(SAPSuccessFactorsError):
    """Base class for all 5xx server errors."""


class SAPSuccessFactorsInternalServerError(SAPSuccessFactorsServer5xxError):
    """500 internal server error."""


class SAPSuccessFactorsBadGatewayError(SAPSuccessFactorsServer5xxError):
    """502 bad gateway."""


class SAPSuccessFactorsServiceUnavailableError(SAPSuccessFactorsServer5xxError):
    """503 service unavailable."""


class SAPSuccessFactorsGatewayTimeoutError(SAPSuccessFactorsServer5xxError):
    """504 gateway timeout."""


ERROR_CODE_EXCEPTION_MAPPING = {
    400: {
        "raise_exception": SAPSuccessFactorsBadRequestError,
        "message": "A validation exception has occurred.",
    },
    401: {
        "raise_exception": SAPSuccessFactorsUnauthorizedError,
        "message": "The access token is invalid or expired.",
    },
    403: {
        "raise_exception": SAPSuccessFactorsForbiddenError,
        "message": "Missing permission for this entity or field.",
    },
    404: {
        "raise_exception": SAPSuccessFactorsNotFoundError,
        "message": "The resource cannot be found.",
    },
    429: {
        "raise_exception": SAPSuccessFactorsRateLimitError,
        "message": "Rate limit exceeded.",
    },
    502: {
        "raise_exception": SAPSuccessFactorsBadGatewayError,
        "message": "Bad gateway.",
    },
    503: {
        "raise_exception": SAPSuccessFactorsServiceUnavailableError,
        "message": "Service temporarily unavailable.",
    },
    504: {
        "raise_exception": SAPSuccessFactorsGatewayTimeoutError,
        "message": "Gateway timeout.",
    },
}
