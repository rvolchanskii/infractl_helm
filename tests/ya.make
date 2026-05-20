PY3TEST()

TEST_SRCS(
    test_puncher.py
    test_balancer.py
)

PEERDIR(
    contrib/python/requests
    contrib/python/pyaml
    taxi/yango/infractl_helm/lib
)

END()
