cmake_minimum_required(VERSION 3.16)
project(scada_selector LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)          # DD-006
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CONNEXTDDS_DIR AND DEFINED ENV{NDDSHOME})
    set(CONNEXTDDS_DIR "$ENV{NDDSHOME}")
endif()
list(APPEND CMAKE_MODULE_PATH "${CONNEXTDDS_DIR}/resource/cmake")

# BUILD_SHARED_LIBS=ON is required -- without it FindRTIConnextDDS resolves the
# static variant and fails with libnddscpp2_release_static-NOTFOUND.
if(NOT DEFINED BUILD_SHARED_LIBS)
    set(BUILD_SHARED_LIBS ON)
endif()

find_package(RTIConnextDDS 7.7.0 REQUIRED COMPONENTS core)
include(ConnextDdsCodegen)

# config.yaml holds the operator-tunable startup defaults (architecture §3.7).
# Prefer a system yaml-cpp; fall back to fetching a pinned release so a fresh
# clone configures without a manual install step.
find_package(yaml-cpp QUIET)
if(NOT yaml-cpp_FOUND)
    include(FetchContent)
    FetchContent_Declare(yaml-cpp
        GIT_REPOSITORY https://github.com/jbeder/yaml-cpp.git
        GIT_TAG        0.8.0
        GIT_SHALLOW    TRUE
    )
    set(YAML_CPP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(YAML_CPP_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
    set(YAML_BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(yaml-cpp)
endif()

# Single source of truth (DD-043): generate compiled C++ types directly from
# the system-level IDL, not a hand-copied duplicate under scada_select/.
connextdds_rtiddsgen_run(
    IDL_FILE         "${CMAKE_CURRENT_SOURCE_DIR}/../dds/idl/PlcValue.idl"
    LANG             "C++11"
    OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated"
    VAR              plc
)

add_library(selection_table STATIC
    src/SelectionTable.cxx
)
target_include_directories(selection_table PUBLIC src)

add_executable(scada_selector
    src/main.cxx
    src/Config.cxx
    src/ControlPlane.cxx
    src/DataPlane.cxx
    src/MetaDataPlane.cxx
    ${plc_CXX11_SOURCES}
    ${plc_CXX11_HEADERS}
)
target_include_directories(scada_selector PRIVATE
    "${CMAKE_CURRENT_BINARY_DIR}/generated"
    src
)
target_link_libraries(scada_selector PRIVATE
    selection_table
    RTIConnextDDS::cpp2_api
    yaml-cpp::yaml-cpp
)

enable_testing()
add_subdirectory(test)
