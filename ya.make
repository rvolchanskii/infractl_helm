PY3_PROGRAM(infractl_manage)

PY_SRCS(
    __main__.py
)

PEERDIR(
    taxi/yango/infractl_helm/lib
)

END()

RECURSE(
    lib
)

RECURSE_FOR_TESTS(
    tests
)
