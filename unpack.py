import argparse
import os
import re

import utils

DEBUG = False
HEADER_SIZE = 16 * utils.KB  # Header size is always 16KB


def main(inputFile, outputDirectory='unpacked'):
    # Vars
    headerScript = ""
    counter = {}
    env = {}  # Environment variables, set by setenv command

    # Parse args
    if not inputFile or not os.path.exists(inputFile):
        print(f"No such file: {inputFile}")
        quit()

    # Create output directory
    utils.createDirectory(outputDirectory)

    # Find header script
    # Header size is 16KB
    # Non used part is filled by 0xFF

    print("[i] Analizing header ...")
    header = utils.loadPart(inputFile, 0, HEADER_SIZE)
    utils.copyPart(inputFile, os.path.join(outputDirectory, "~header"), 0, HEADER_SIZE)

    offset = header.find(b'\xff')
    if offset != -1:
        headerScript = header[:offset].decode()
    else:
        print("[!] Could not find header script!")
        quit()

    if DEBUG:
        print(headerScript)

    # Save the script
    print(f"[i] Saving header script to {os.path.join(outputDirectory, '~header_script.sh')} ...")
    with open(os.path.join(outputDirectory, "~header_script.sh"), "w") as f:
        f.write(headerScript)

    # Parse script
    print("[i] Parsing script ...")
    sparseList = []
    # Supporting filepartload, mmc, store_secure_info, store_nuttx_config
    for line in headerScript.splitlines():

        if DEBUG:
            print(line)

        if re.match("^setenv", line):
            params = utils.processSetEnv(line)
            key = params["key"]
            if "value" not in params:
                del env[key]
            else:
                value = params["value"]
                env[key] = value
                print(f"[i] Parsing setenv {key} -> {value}")

        if re.match("^filepartload", line):
            line = utils.applyEnv(line, env)
            params = utils.processFilePartLoad(line)
            offset = params["offset"]
            size = params["size"]

        if re.match("^store_secure_info", line):
            line = utils.applyEnv(line, env)
            params = utils.processStoreSecureInfo(line)
            outputFile = os.path.join(outputDirectory, params["partition_name"])
            utils.copyPart(inputFile, outputFile, int(offset, 16), int(size, 16))

        if re.match("^store_nuttx_config", line):
            line = utils.applyEnv(line, env)
            params = utils.processStoreNuttxConfig(line)
            outputFile = os.path.join(outputDirectory, params["partition_name"])
            utils.copyPart(inputFile, outputFile, int(offset, 16), int(size, 16))

        if re.match("^multi2optee", line):
            line = utils.applyEnv(line, env)
            params = utils.processMulti2optee(line)
            outputFile = os.path.join(outputDirectory, params["partition_name"] + ".bin")
            utils.copyPart(inputFile, outputFile, int(offset, 16), int(size, 16))
            print("[i] Partition: {}\tOffset: {}\tSize {} ({}) -> {}".format(params["partition_name"], offset, size,
                                                                             utils.sizeStr(int(size, 16)), outputFile))

        if re.match("^sparse_write", line):
            line = utils.applyEnv(line, env)
            params = utils.processSparseWrite(line)
            outputFile = utils.generateFileNameSparse(outputDirectory, params)
            print("[i] Partition: {}\tOffset: {}\tSize {} ({}) -> {}".format(params["partition_name"], offset, size,
                                                                             utils.sizeStr(int(size, 16)), outputFile))
            if not params["partition_name"] in sparseList:
                sparseList.append(params["partition_name"])
            utils.copyPart(inputFile, outputFile, int(offset, 16), int(size, 16))

        if re.match("^mmc", line):
            line = utils.applyEnv(line, env)
            params = utils.processMmc(line)

            if params:

                # if params["action"] == "create":
                # 	nothing here

                if params["action"] == "write.boot":
                    outputFile = utils.generateFileName(outputDirectory, params, ".img")
                    utils.copyPart(inputFile, outputFile, int(offset, 16), int(size, 16))
                    print("[i] Partition: {}\tOffset: {}\tSize {} ({}) -> {}".format(params["partition_name"], offset,
                                                                                     size,
                                                                                     utils.sizeStr(int(size, 16)),
                                                                                     outputFile))

                if params["action"] == "write.p":
                    outputFile = os.path.join(outputDirectory, params["partition_name"] + ".img")
                    utils.copyPart(inputFile, outputFile, int(offset, 16), int(size, 16))
                    print("[i] Partition: {}\tOffset: {}\tSize {} ({}) -> {}".format(params["partition_name"], offset,
                                                                                     size,
                                                                                     utils.sizeStr(int(size, 16)),
                                                                                     outputFile))

                if params["action"] == "write.p.continue":
                    outputFile = os.path.join(outputDirectory, params["partition_name"] + ".img")
                    utils.copyPart(inputFile, outputFile, int(offset, 16), int(size, 16), append=True)
                    print(
                        "[i] Partition: {}\tOffset: {}\tSize {} ({}) append to {}".format(params["partition_name"],
                                                                                          offset,
                                                                                          size,
                                                                                          utils.sizeStr(int(size, 16)),
                                                                                          outputFile))

                if params["action"] == "unlzo":
                    outputLzoFile = utils.generateFileName(outputDirectory, params, ".lzo")
                    outputImgFile = utils.generateFileName(outputDirectory, params, ".img")
                    # save .lzo
                    print("[i] Partition: {}\tOffset: {}\tSize {} ({}) -> {}".format(params["partition_name"], offset,
                                                                                     size,
                                                                                     utils.sizeStr(int(size, 16)),
                                                                                     outputLzoFile))
                    utils.copyPart(inputFile, outputLzoFile, int(offset, 16), int(size, 16))
                    # unpack .lzo -> .img
                    print("[i]     Unpacking LZO (Please be patient) {} -> {}".format(outputLzoFile, outputImgFile))
                    utils.unlzo(outputLzoFile, outputImgFile)
                    # delete .lzo
                    os.remove(outputLzoFile)

                if params["action"] == "unlzo.continue":
                    if not params["partition_name"] in counter:
                        counter[params["partition_name"]] = 0
                    counter[params["partition_name"]] += 1

                    outputImgFile = os.path.join(outputDirectory, params["partition_name"] + ".img")
                    outputChunkLzoFile = os.path.join(outputDirectory, params["partition_name"] + str(
                        counter[params["partition_name"]]) + ".lzo")
                    outputChunkImgFile = os.path.join(outputDirectory, params["partition_name"] + str(
                        counter[params["partition_name"]]) + ".img")
                    # save .lzo
                    print(
                        f"[i] Partition: {params['partition_name']}\tOffset: {offset}\tSize {size} ({utils.sizeStr(int(size, 16))}) -> {outputChunkLzoFile}")
                    utils.copyPart(inputFile, outputChunkLzoFile, int(offset, 16), int(size, 16))
                    # unpack chunk .lzo -> .img
                    print(
                        f"[i]     Unpacking LZO (Please be patient) {outputChunkLzoFile} -> {outputChunkImgFile}")
                    utils.unlzo(outputChunkLzoFile, outputChunkImgFile)
                    # append the chunk to main .img
                    print(f"[i]     {outputChunkImgFile} append to {outputImgFile}")
                    utils.appendFile(outputChunkImgFile, outputImgFile)
                    # delete chunk
                    os.remove(outputChunkLzoFile)
                    os.remove(outputChunkImgFile)
    for partName in sparseList:
        print(f"[i] Sparse: converting {partName}_sparse.* to {partName}.img")
        sparseFiles = os.path.join(outputDirectory, partName + '_sparse.*')
        sparseFilesConv = sparseFiles.replace("\\", "/")
        outputImgFile = os.path.join(outputDirectory, partName + ".img")
        utils.sparse_to_img(sparseFilesConv, outputImgFile)
        os.system(f'del {sparseFiles}' + sparseFiles)
    print("[i] Done.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="mstar-bin-tool unpack.py v.1.2_sha-man (modify by https://github.com/ColdWindScholar/)")
    parser.add_argument('firmware', default=None, help='firmware to unpack')
    parser.add_argument('output', default='unpacked', help="<output folder [default: ./unpacked/]>")
    args = parser.parse_args()
    main(args.firmware, args.output)