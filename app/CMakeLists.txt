add_executable(nvme_simulator main.cpp)
target_include_directories(nvme_simulator PRIVATE "${PROJECT_SOURCE_DIR}")

set_target_properties(nvme_simulator PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
