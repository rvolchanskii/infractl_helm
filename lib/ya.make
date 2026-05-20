PY3_LIBRARY()

PY_NAMESPACE(infractl_helm.lib)

PY_SRCS(
    __init__.py
    puncher.py
)

PEERDIR(
    contrib/python/requests
    contrib/python/pyaml
)

END()
