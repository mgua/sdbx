import json
import struct
from pathlib import Path
from typing import Optional, Dict, Any
import torch
import os
from os.path import basename as basedname
import tomllib
from collections import defaultdict
from sdbx import config
from sdbx.config import config, config_source_location

from functools import cache
from typing import Callable, Dict
from dataclasses import dataclass
from sdbx.config import DTYPE_T, TensorData
import networkx as nx
from networkx import MultiDiGraph

source = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_source_location = os.path.join(source, "config")

class ReadMeta: # instance like so - instance = ReadMeta(full_path).data(filename, full_path)
    full_data = {}
    known = {}
    occurrence_counts = defaultdict(int)
    count_dict = {} # level of certainty, counts tensor block type matches
    model_tag = {  # measurements and metadata detected from the model
                "filename": "",
                "size": "",
                "dtype": "",
                "tensor_params": 0,
                "shape": "",
                "__metadata__": "",
                "info.files_metadata": "",
                "file_metadata": "",
                "name": "",
                "info.sharded": "",
                "info.metadata": "",
                "file_metadata.tensors": "",
                "modelspec.title": "",
                "modelspec.architecture": "",
                "modelspec.author": "",
                "modelspec.hash_sha256": "",
                "modelspec.resolution": "",
                "resolution": "",
                "ss_resolution": "",
                "ss_mixed_precision": "",
                "ss_base_model_version": "",
                "ss_network_module": "",
                "model.safetensors": "",
                "ds_config": "",
    }

    def __init__(
        self, full_path, filename=""
    ):
        self.full_path = full_path #the path of the file
        self.filename = filename #the title of the file only
        if not os.path.exists(self.full_path): #be sure it exists, then proceed
            raise RuntimeError(f"Not found: {self.filename}")
        else:
            self.model_tag["filename"] = self.filename
            self.model_tag["size"] = os.path.getsize(self.full_path)

    @classmethod
    def _parse_safetensors_metadata(self, full_path):
        with open(full_path, "rb") as f:
            header = struct.unpack("<Q", f.read(8))[0]
            return json.loads(f.read(header), object_hook=self._search_dict)

    @classmethod
    def data(self, filename, full_path):
        if Path(filename).suffix in {".pt", ".pth"}:  # yes, this will be slow
            # Access model's metadata (e.g., layer names and parameter shapes)
            model = torch.load(full_path, map_location="cpu")
            for p in model.named_parameters():
                print(f"Data: {p}, Size: {p.size()}")

        elif Path(filename).suffix in {".safetensors" or ".sft"}:
            self.occurrence_counts.clear()  # scrub dictionaries
            self.count_dict.clear()
            self.full_data.clear()
            self.known.clear()
            self.meta = self._parse_safetensors_metadata(full_path) #analyse file contents
            self.full_data.update((k,v) for k,v in self.model_tag.items() if v != "") #make a new dict with all attributes
            self.full_data.update((k,v) for k,v in self.count_dict.items() if v != 0) #part 2 dict boogaloo
            class_key = list(self.count_dict.keys()) # key listing all model types
            self.model_tag.clear() # clean up lingering values
            self.meta.clear() #dump file contents
            return class_key, self.full_data

        elif Path(filename).suffix in {".gguf"}:
            meta = ""  # placeholder - parse gguf metadata(path) using llama lib
        else:
            raise RuntimeError(f"Unknown file format: {filename}")

    @classmethod
    def _search_dict(self, meta):
        self.meta = meta
        if self.meta.get("__metadata__", "not_found") != "not_found": #bounce back from missing keys
            self.model_tag["__metadata__"] = meta.get("__metadata__")
        model_classes = Path(os.path.join(config_source_location, "classify.toml"))
        with open(model_classes, "rb") as f:
            self.types = tomllib.load(f)  # Load the TOML contents into 'types'
        for key, value in self.types.items(): # Check if the value is a multiline string
            if isinstance(value, str): # Split  multiline string into lines and strip whitespace
                self.items = [item.strip() for item in value.strip().split('\n') if item.strip()] #get rid of newlines and whitespace
                self.known[key] = {i: item for i, item in enumerate(self.items)} # Create dictionary
        for key, values in self.known.items():  #model type, dict data
            for i, value in values.items():      #dict data to key pair
                for num in self.meta:         #extracted metadata as values
                    if value in num:     #if value matches one of our key values
                        self.occurrence_counts[value] += 1 #count matches
                self.count_dict[key] = self.occurrence_counts.get(value, 0)  #pair match count with type of model

        for key, value in self.model_tag.items(): #look at the tags in the file
            if self.meta.get(key, "not_found") != "not_found": #handle inevitable exceptions invisibly
                if self.model_tag[key] == "":  #be sure the value isnt empty
                    self.model_tag[key] = meta.get(key)  #drop it like its hot
                if key == "dtype": #counting these keys reveals tensor count
                    self.model_tag["tensor_params"] += 1
                if key == "shape": #
                    if meta.get(key) > self.model_tag["shape"]:  #measure first shape size thats returned
                        self.model_tag["shape"] = self.meta.get(key)  # (room for improvement here, would prefer to be largest shape, tbh)
        return meta
        # fetch gguf data    

class NodeTuner:
    def __init__(self, fn):
        self.fn = fn
        self.name = fn.info.fname

    @cache
    def get_tuned_parameters(self, widget_inputs, model_types, metadata):
        max_value = max(metadata.values())
        largest_keys = [k for k, v in metadata.items() if v == max_value] # collect the keys of the largest pairs
        
        # size 50mb-850mb - vae
        # sie 5-500mb pth - upscale (aura sr* 2gb .safetensors)
        # vae shape? [512, 512, 3, 3]
        #
        # if unet - text interpreter (diffusion?)
        # if transformer - text interpreter(transformers)
        # mmdit -
        # flux -
        # pixxart s
        # sd - enable pcm, ays
        # if hunyuan - 
        # if diffusers - image interpreter (diffusers)
        # if sdxl - enable pcm, ays option, force upcast vae if default vae, otherwise use fp16
        # if transformers - text model
        # compare the values and assign sensible variables
        # generate dict of tuned parameters like below:
        # return the dict

        # tuned parameters & hyperparameters only!! pcm parameters here 

        # return {
        #     "function name of node": {
        #         "parameter name": "parameter value",
        #         "parameter name 2": "parameter value 2"
        #     }
        co

    def collect_tuned_parameters(self, node_manager, graph: MultiDiGraph, node_id: str):
        predecessors = graph.predecessors(node_id)

        node = graph.nodes[node_id]

        tuned_parameters = {}
        for p in predecessors:
            pnd = graph.nodes[p]  # predecessor node data
            pfn = node_manager.registry[pnd['fname']]  # predecessor function

            p_tuned_parameters = pfn.tuner.get_tuned_parameters(pnd['widget_inputs'])[node['fname']]

            tuned_parameters |= p_tuned_parameters
        
        return tuned