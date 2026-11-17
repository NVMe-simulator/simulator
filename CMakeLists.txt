cmake_minimum_required(VERSION 3.24)
project(nvme_simulator LANGUAGES CXX)

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_BINARY_DIR)
    message(FATAL_ERROR "Use an out-of-source build: cmake --preset dev")
endif()

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

add_subdirectory(src)
add_subdirectory(app)

find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)

add_custom_target(lint
    COMMAND "${CMAKE_COMMAND}" -E env "CXX=${CMAKE_CXX_COMPILER}"
        "${Python3_EXECUTABLE}" tools/lint.py
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    VERBATIM)
add_custom_target(format
    COMMAND "${Python3_EXECUTABLE}" tools/lint.py --format
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    VERBATIM)
