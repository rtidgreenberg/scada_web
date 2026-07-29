# Makes dds/ importable as a package so `dds.gen.PlcValue` is a stable,
# centralized import path for the rtiddsgen-generated Python types shared by
# every component (scada_web, sim, tests). idl/ and qos/ remain plain data
# directories (IDL source, QoS profiles XML) with no Python of their own.
