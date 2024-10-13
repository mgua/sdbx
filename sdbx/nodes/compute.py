"""
Credits:
Felixsans
"""
import gc
import os
import torch
import datetime
from time import perf_counter_ns
from collections import defaultdict

from diffusers.schedulers import (
    EulerDiscreteScheduler,
    EulerAncestralDiscreteScheduler,
    FlowMatchEulerDiscreteScheduler,
    EDMDPMSolverMultistepScheduler,
    DPMSolverMultistepScheduler,
    DDIMScheduler,
    LCMScheduler,
    TCDScheduler,
    AysSchedules,          
    HeunDiscreteScheduler,
    UniPCMultistepScheduler,
    LMSDiscreteScheduler,
    DEISMultistepScheduler,
     )
from diffusers.utils import logging as df_log
from transformers import logging as tf_log
from diffusers import AutoencoderKL, AutoPipelineForText2Image
from transformers import CLIPTextModel, CLIPTokenizer, CLIPTextModelWithProjection
import accelerate

from sdbx import logger
from sdbx.config import config
from sdbx.nodes.helpers import seed_planter

class T2IPipe:
    # __call__? NO __init__! ONLY __call__. https://huggingface.co/docs/diffusers/main/en/api/pipelines/auto_pipeline#diffusers.AutoPipelineForText2Image

    config_path = config.get_path("models.metadata")
    spec = config.get_default("spec","data")
    device = next(iter(spec.get("devices","cpu")),"cpu")

############## TIMECODE
    def tc(self, clock): 
        return print(f"[ {str(datetime.timedelta(milliseconds=(((perf_counter_ns()-clock)*1e-6))))[:-2]} ]") 

############## STFU HUGGINGFACE
    def hf_log(self, on=False, fatal=False):
        if on == True:
            tf_log.enable_default_handler()
            df_log.enable_default_handler()
            tf_log.set_verbosity_warning()
            df_log.set_verbosity_warning()
        if fatal == True:
            tf_log.disable_default_handler()
            df_log.disable_default_handler()
            tf_log.set_verbosity(tf_log.FATAL)
            tf_log.set_verbosity(df_log.FATAL)
        else:
            tf_log.set_verbosity_error()
            df_log.set_verbosity_error()

############## TORCH DATATYPE
    def float_converter(self, old_index):
        float_chart = {
                "F64": ["fp64", torch.float64],
                "F32": ["fp32", torch.float32],
                "F16": ["fp16", torch.float16],
                "BF16": ["bf16", torch.bfloat16],
                "F8_E4M3": ["fp8e4m3fn", torch.float8_e4m3fn],
                "F8_E5M2": ["fp8e5m2", torch.float8_e5m2],
                "I64": ["i64", torch.int64],
                "I32": ["i32", torch.int32],
                "I16": ["i16", torch.int16],
                "I8": ["i8", torch.int8],
                "U8": ["u8", torch.uint8],                                       
                "NF4": ["nf4", "nf4"],
        }
        for key, val in float_chart.items():
            if old_index == key:
                return val[0], val[1]

############## SCHEDULER
    def algorithm_converter(self, non_constant, exp):
        self.non_constant = non_constant
        self.algo_exp = exp
        self.schedule_chart = {
            "EulerDiscreteScheduler" : EulerDiscreteScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp),           
            "EulerAncestralDiscreteScheduler" : EulerAncestralDiscreteScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp),
            "FlowMatchEulerDiscreteScheduler" : FlowMatchEulerDiscreteScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp),     
            "EDMDPMSolverMultistepScheduler" : EDMDPMSolverMultistepScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp), 
            "DPMSolverMultistepScheduler" : DPMSolverMultistepScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp),        
            "DDIMScheduler" : DDIMScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp),
            "LCMScheduler" : LCMScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp),
            "TCDScheduler" : TCDScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp),
            "AysSchedules": AysSchedules,
            "HeunDiscreteScheduler" : HeunDiscreteScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp),
            "UniPCMultistepScheduler" : UniPCMultistepScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp),
            "LMSDiscreteScheduler" : LMSDiscreteScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp),  
            "DEISMultistepScheduler" : DEISMultistepScheduler.from_config(self.pipe.scheduler.config,**self.algo_exp),
        }
        if self.non_constant in self.schedule_chart:
            self.pipe.scheduler = self.schedule_chart[self.non_constant]
            self.tc(self.clock)
            return self.pipe.scheduler
        else:
            try:
                raise ValueError(f"Scheduler '{self.non_constant}' not supported")
            except ValueError as error_log:
                logger.debug(f"Scheduler error {error_log}.", exc_info=True)

############## QUEUE
    def queue_manager(self, prompt, seed):
        self.clock = perf_counter_ns() # 00:00:00
        self.tc(self.clock)
        self.tc(self.clock)
        self.queue = []    

        self.queue.extend([{
            "prompt": prompt,
            "seed": seed,
            }])
        
############## ENCODERS
    def declare_encoders(self, exp):
        self.tformer, self.gen, self.enc_opt = exp
        self.tformer_dict = {}
        i = 0
        for each in self.tformer["variant"]:
            if self.tformer.get("variant",0) != 0:
                var, dtype = self.float_converter(self.tformer[each]["variant"][next(iter(self.tformer[each]["variant"]),0)])
                self.tformer_dict.setdefault("variant",var)
                self.tformer_dict.setdefault("torch_dtype", dtype)
            if self.enc_opt.get("attn_implementation",0) != 0: 
                self.tformer_dict.setdefault("attn_implementation", self.enc_opt["attn_implementation"])
            i += 1
        self.tc(self.clock)

        self.tokenizer = CLIPTokenizer.from_pretrained(
            self.enc_opt["transformer"][0],
            subfolder="tokenizer"
        )
        self.hf_log(fatal=True) #suppress layer skip messages
        self.text_encoder = CLIPTextModel.from_pretrained(
            self.enc_opt["transformer"][0],
            subfolder="text_encoder",
            **self.tformer_dict
        ).to(self.device)
        self.hf_log(on=True) #return to normal
      
        if self.enc_opt.get("dynamo",0) != 0:
            self.compile_model(self.text_encoder, self.enc_opt["compile"])

        self.tokenizer_2 = CLIPTokenizer.from_pretrained( #CLIPTokenizerFast.from_pretrained(
            self.enc_opt["transformer"][1],
            subfolder="tokenizer_2"
        )

        self.hf_log(fatal=True) #suppress layer skip messages
        self.text_encoder_2 = CLIPTextModelWithProjection.from_pretrained(
            self.enc_opt["transformer"][1],
            subfolder="text_encoder_2",
            **self.tformer_dict
        ).to(self.device)
        self.hf_log(on=True) #return to normal
        if self.enc_opt.get("dynamo",0) != 0:
            self.compile_model(self.text_encoder_2, self.enc_opt["compile"])

############## EMBEDDINGS
    def generate_embeddings(self, prompts, tokenizers, text_encoders, exp):
        self.emb_exp = exp
        self.tc(self.clock)
        embeddings_list = []
        #for prompt, tokenizer, text_encoder in zip(prompts, self.tokenizer.values(), self.text_encoder.values()):
        for prompt, tokenizer, text_encoder in zip(prompts, tokenizers, text_encoders):
            cond_input = tokenizer(
            prompt,
            max_length=tokenizer.model_max_length,
            **self.emb_exp
        )
            prompt_embeds = text_encoder(cond_input.input_ids.to(self.device), output_hidden_states=True)

            pooled_prompt_embeds = prompt_embeds[0]
            embeddings_list.append(prompt_embeds.hidden_states[-2])

            prompt_embeds = torch.concat(embeddings_list, dim=-1)

        negative_prompt_embeds = torch.zeros_like(prompt_embeds)
        negative_pooled_prompt_embeds = torch.zeros_like(pooled_prompt_embeds)

        bs_embed, seq_len, _ = prompt_embeds.shape
        prompt_embeds = prompt_embeds.repeat(1, 1, 1)
        prompt_embeds = prompt_embeds.view(bs_embed * 1, seq_len, -1)

        seq_len = negative_prompt_embeds.shape[1]
        negative_prompt_embeds = negative_prompt_embeds.repeat(1, 1, 1)
        negative_prompt_embeds = negative_prompt_embeds.view(1 * 1, seq_len, -1)

        pooled_prompt_embeds = pooled_prompt_embeds.repeat(1, 1).view(bs_embed * 1, -1)
        negative_pooled_prompt_embeds = negative_pooled_prompt_embeds.repeat(1, 1).view(bs_embed * 1, -1)
        return prompt_embeds, negative_prompt_embeds, pooled_prompt_embeds, negative_pooled_prompt_embeds

############## PROMPT
    def encode_prompt(self, exp):
        self.enc_exp = exp
        with torch.no_grad():
            for generation in self.queue:
                generation['embeddings'] = self.generate_embeddings(
                    [generation['prompt'], generation['prompt']],
                    [self.tokenizer, self.tokenizer_2],
                    [self.text_encoder, self.text_encoder_2],
                    self.enc_exp
                    )

############## CACHE MANAGEMENT
    def cache_jettison(self, encoder=False, lora=False, unet=False, vae=False):
        self.tc(self.clock)
        if encoder: del self.tokenizer, self.text_encoder,  self.tokenizer_2, self.text_encoder_2
        if lora: self.pipe.unload_lora_weights()
        if unet: del self.pipe.unet
        if vae: del self.pipe.vae
        gc.collect()
        if self.device == "cuda": torch.cuda.empty_cache()
        if self.device == "mps": torch.mps.empty_cache()
        if self.device == "xpu": torch.xpu.empty_cache()
 

############## PIPE
    def construct_pipe(self, exp, vae):
        self.pipe_exp, self.model, = exp
        self.vae_opt, self.vae_exp = vae
        if self.pipe_exp.get("variant",0):
            var, dtype = self.float_converter(self.pipe_exp["variant"])
            self.pipe_exp["variant"] = var
            self.pipe_exp.setdefault("torch_dtype", dtype)
        self.tc(self.clock)


        self.autoencoder = self.vae_opt["vae"] #autoencoder wants full path and filename 
        if self.vae_exp.get("variant",0) != 0:
            var, dtype = self.float_converter(self.vae_exp["variant"])
            self.vae_exp["variant"] = var
            self.vae_exp.setdefault("torch_dtype", dtype)
        self.autoencoder = AutoencoderKL.from_single_file(self.autoencoder,**self.vae_exp).to(self.device)

        self.tc(self.clock)
        self.pipe = AutoPipelineForText2Image.from_pretrained(self.model, vae=self.autoencoder, **self.pipe_exp).to(self.device)

############## LORA
    def add_lora(self, exp, fuse, opt):
        self.lora_exp = exp
        self.lora_opt = opt
        lora = os.path.basename(self.lora_exp)
        lora_path = self.lora_exp.replace(lora,"")
        self.tc(self.clock) # lora2
        self.pipe.load_lora_weights(lora_path, weight_name=lora)
        if fuse: 
            self.pipe.fuse_lora(**self.lora_opt) #add unet only possibility
            self.tc(self.clock)

############## MEMORY OFFLOADING
    def offload_to(self, seq=False, cpu=False, disk=False):
        self.tc(self.clock) 
        if not "cpu" in self.device:
            if seq == True: self.pipe.enable_sequential_cpu_offload()
            elif cpu == True: self.pipe.enable_model_cpu_offload() 
        elif disk == True: accelerate.disk_offload() 

############## COMPILE
    def compile_model(self, model, exp):
        self.model = model
        if "cuda" in self.device:
            exp.setdefault("mode","max-autotune")
        if False:self.model = torch.compile(self.model, **exp) #compile needs to be put in another routine
        return self.model
    
############## INFERENCE
    def diffuse_latent(self, exp):
        tformer, self.gen_dict, self.opt_exp = exp
        self.tc(self.clock)
        self.pipe.scheduler = self.algorithm_converter(self.opt_exp["algorithm"], self.opt_exp["scheduler"])

        self.tc(self.clock) ### cue lag spike
        if self.opt_exp.get("lora",0) !=0:
            self.add_lora(self.opt_exp["lora"], self.opt_exp["fuse_lora_on"], self.opt_exp["fuse_lora"])
        if self.enc_opt.get("dynamo",0) != 0:
            self.compile_model(self.pipe.unet, self.opt_exp["compile"])

        self.tc(self.clock)
        generator = torch.Generator(device=self.device)
        if self.opt_exp.get("seq",0) !=0 or self.opt_exp.get("cpu",0) !=0 or self.opt_exp.get("disk",0) != 0: self.offload_to(self.opt_exp["seq"], self.opt_exp["cpu"], self.opt_exp["disk"])

        self.tc(self.clock)
        self.image_start = perf_counter_ns()
        self.individual_totals = []
        for i, generation in enumerate(self.queue, start=1):
            self.tc(self.clock)
            seed_planter(generation['seed'])
            generator.manual_seed(generation['seed'])
            self.individual_start = perf_counter_ns()
            self.tc(self.clock)
            #self.tc(self.image_start, f"{i} of {len(self.queue)}", self.bug_off) 
            
            generation['latents'] = self.pipe(
                prompt_embeds=generation['embeddings'][0],
                negative_prompt_embeds =generation['embeddings'][1],
                pooled_prompt_embeds=generation['embeddings'][2],
                negative_pooled_prompt_embeds=generation['embeddings'][3],
                **self.gen_dict
            ).images

############## AUTODECODE
    def decode_latent(self, opt):
        self.vae_opt, self.vae_exp = opt
        # self.autoencoder = self.vae_opt["vae"] #autoencoder wants full path and filename 
        # if self.vae_exp.get("variant",0) != 0:
        #     var, dtype = self.float_converter(self.vae_exp["variant"])
        #     self.vae_exp["variant"] = var
        #     self.vae_exp.setdefault("torch_dtype", dtype)
        file_prefix = f"{self.vae_opt['file_prefix']}-{self.vae_opt['lora_class']}-{self.vae_opt['algorithm']}"
        # self.tc(self.clock) f"decode configured for {os.path.basename(self.autoencoder)}...", self.bug_off)
        # self.autoencoder = AutoencoderKL.from_single_file(self.autoencoder,**self.vae_exp).to(self.device)
        # self.pipe.vae = self.autoencoder
        if self.vae_opt.get("upcast_vae",0) != 0: 
            self.pipe.upcast_vae()
        if self.enc_opt.get("dynamo",0) != 0:
            self.pipe.vae.decode = self.compile_model(self.pipe.vae.decode, self.vae_opt["compile"])
        with torch.no_grad():
            counter = [s.endswith('png') for s in os.listdir(config.get_path("output"))].count(True) # get existing images
            self.tc(self.clock)
            for i, generation in enumerate(self.queue, start=1):
                self.seed = generation['seed']
                self.tc(self.image_start) 
                generation['latents'] = generation['latents'].to(next(iter(self.pipe.vae.post_quant_conv.parameters())).dtype)

                image = self.pipe.vae.decode(
                    generation['latents'] / self.pipe.vae.config.scaling_factor,
                    return_dict=False,
                )[0]

                image = self.pipe.image_processor.postprocess(image)[0] #, output_type='pil')[0]

                self.tc(self.clock)
                counter += 1
                filename = f"{file_prefix}-{self.seed}-{counter}-batch-{i}.png"

                image.save(os.path.join(config.get_path("output"), filename)) # optimize=True,     
                self.tc(self.clock)
                        
############## MEASUREMENT SUMMARY
    def metrics(self):

        if "cuda" in self.device:
            memory = round(torch.cuda.max_memory_allocated(self.device) * 1e-9, 2)
            self.tc(self.clock)