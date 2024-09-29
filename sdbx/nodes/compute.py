"""
Credits:
Felixsans
"""

import gc
import os
import platform
from time import perf_counter
import datetime
import time
from collections import defaultdict

from sdbx.nodes.tuner import NodeTuner
from diffusers import AutoPipelineForText2Image, AutoencoderKL, DDIMScheduler, EulerAncestralDiscreteScheduler, EulerDiscreteScheduler, FromOriginalModelMixin
from diffusers.schedulers import AysSchedules
from sdbx.config import config
from sdbx.nodes.helpers import seed_planter, soft_random, get_gpus
import torch
from transformers import CLIPTextModel, PreTrainedTokenizerFast, CLIPTokenizer, CLIPTokenizerFast

#def tc(): print(str(datetime.timedelta(seconds=time.process_time())), end="")

class Inference:
    configs = os.path.join(config.get_path("models.metadata"),"vae")

    def test_process(self):
        filename= "tPonynai3_v55.safetensors"
        path = config.get_path("models.image")
        self.device = "cuda"
        print("beginning")
        print(os.path.join(path,filename))
        self.default = NodeTuner().determine_tuning(filename)
        self.model_class = self.default["model"]["class"]
        print(self.default)
        if self.default != None:
            seed=soft_random()
            self.prompt_handler(seed)
            self.declare_encoders()
            var_list = [
                "__doc__",
                "__name__",
                "__package__",
                "__loader__",
                "__spec__",
                "__annotations__",
                "__builtins__",
                "__file__",
                "__cached__",
                "config",
                "indexer",
                "json",
                "os",
                "defaultdict",
                "IndexManager",
                "logger",
                "psutil",
                "var_list",
                "i"
                ]
            variables = dict(locals())
            for each in variables:
                if each not in var_list:
                    print(f"{each} = {variables[each]}")



    def prompt_handler(self, seed):
        queue = []
        queue.extend([{
        "prompt": self.default["pipe"]["prompt"],
        "seed": seed,
        }])

    def declare_encoders(self):
        tokenizer = defaultdict(dict)
        text_encoder = defaultdict(dict)
        #print(text_encoder)
        i=0
        tokenizer = defaultdict(list)
        text_encoder = defaultdict(list)
        for each in self.default["transformer"]["file"]:
            self.class_name = each
            self.weights = self.default["transformer"]["file"][each][1]
            self.symlnk_path = os.path.join(self.configs,self.class_name) #autoencoder also wants specific filenames
            self.dtype = self.default["transformer"]["file"][each][2]
            self.symlnk_file = os.path.join(self.symlnk_path,f"model.safetensors")
            if os.path.isfile(self.symlnk_file): os.remove(self.symlnk_file)
            #huggingface song and dance
                                                #make tf class dynamic
            if self.default["transformer"]["use_fast"]:
                tokenizer[i] = CLIPTokenizerFast.from_pretrained(
                    self.symlnk_path,
                    #subfolder='tokenizer',
                )
                                                #make tf class dynamic
            else:
                tokenizer[i] = CLIPTokenizer.from_pretrained(
                    self.symlnk_path,
                    #subfolder='tokenizer',
                )

            os.symlink(self.weights,self.symlnk_file) #note: no 'i' in 'symlnk'
            text_encoder[i] = CLIPTextModel.from_pretrained(
                self.symlnk_path,
                #subfolder='text_encoder',
                #use_safetensors=True,
                torch_dtype=self.dtype[1],
                variant=self.dtype[0],
            ).to(self.device)
            i += 1


    def encode_prompt(self, prompts, tokenizers, text_encoders):
       # print(f"{tc()} encoding prompt with device: {self.device}...") #debug
        embeddings_list = []

        for prompt, tokenizer, text_encoder in zip(prompts, tokenizers, text_encoders):
            cond_input = tokenizer(
            prompt,
            max_length=tokenizer.model_max_length,
            padding='max_length',
            truncation=True,
            return_tensors='pt',
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

        with torch.no_grad():
            for generation in queue:
                generation['embeddings'] = encode_prompt(
                    [generation['prompt'], generation['prompt']],
                    [tokenizer, tokenizer_2],
                    [text_encoder, text_encoder_2],
            )

        # EMPTY CACHEal
        if clear_cache:
            del tokenizer, text_encoder, tokenizer_2, text_encoder_2
            gc.collect()
            if device == "cuda": torch.cuda.empty_cache()
            if device == "mps": torch.mps.empty_cache()

        ### USER OPTIONS  : INFERENCE
        model = next(iter(m for m in os.listdir(config.get_path("models.checkpoints")) if "adfdfd" in m and m.endswith(".safetensors")), "stabilityai/stable-diffusion-xl-base-1.0")
        lora = next(iter(m for m in os.listdir(config.get_path("models.loras")) if "adfdfd" in m and m.endswith(".safetensors")), "pcm_sdxl_normalcfg_8step_converted_fp16.safetensors") #lora needs to be explicitly declared
        scheduler =  next(iter(m for m in get_schedulers("EulerAncestral")), "EulerDiscreteScheduler")
        inference_steps=8 # only appears if Lora isnt a PCM/LCM and scheduler isnt "AysScheduler". lower to increase speed
        guidance_scale=5, # default for sdxl-architecture. raise for sd-architecture, drop to 0 (off) to increase speed with turbo, etc. auto mode?
        # lora2 = next(iter(m for m in os.listdir(config.get_path("models.loras")) if "adfdfd" in m and m.endswith(".safetensors")), "a default lora.safetensors")
        # text_inversion = next((w for w in get_dir_files("models.embeddings"," ")),"None")

        ### AUTOCONFIG OPTIONS : INFERENCE
        sequential_offload = True #[universal] lower vram use (and speed on pascal apparently!!)
        precision='16' # [universal], less memory for trivial quality decrease
        dynamic_guidance = True # [universal] half cfg @ 50-75%. sdxl architecture only. playground, vega, ssd1b, pony. bad for pcm
        model_ays = "StableDiffusionXLTimesteps" #[compataibility] for alignyoursteps to match model type
        cpu_offload = False  #[compatability] lower vram use by pushing to cpu
        bf16=False # [compatability] certain types of models need this, it influences determinism as well
        timestep_spacing="trailing" #[compatability] DDIM, PCM "trailing"
        clip_sample = False #[compatability] PCM False
        set_alpha_to_one = False, #[compatability]PCM False 
        rescale_betas_zero_snr=True #[compatability] DDIM True
        disk_offload = False #[compatability] last resort, but things work

        ### INFERENCE SYSTEM
        lora_path = config.get_path("models.loras")
        pipe_args = {
            "use_safetensorelifs": True,
            "tokenizer":None,
            "text_encoder":None,
            "tokenizer_2":None,
            "text_encoder_2":None,
        }

        if precision=='ema':
            pipe_args["variant"]="ema" 
        elif precision=='16':
            pipe_args["variant"]="fp16"
            pipe_args["torch_dtype"]=torch.bfloat16 if bf16 else torch.float16

        print(f"{tc()} precision set for: {precision}, bfloat: {bf16}, using {pipe_args["torch_dtype"]}") #debug

        print(f"{tc()} load model {model}...") #debug
        pipe = AutoPipelineForText2Image.from_pretrained(
            model,**pipe_args,                        
        ).to(device)

        print(f"{tc()} set scheduler, lora = {os.path.join(lora_path, lora)}")  # lora2
        scheduler_args = {
        
        }

        if scheduler=="DDIMScheduler":
            scheduler_args[ "timestep_spacing"]=timestep_spacing
            scheduler_args["rescale_betas_zero_snr"]=rescale_betas_zero_snr #[compatability] DDIM, v-pred?
            if lora:
                scheduler_args["clip_sample"]=clip_sample #[compatability] PCM
                scheduler_args["set_alpha_to_one"]=set_alpha_to_one, #[compatability]PCM
        # if scheduler=="DPMMultiStepScheduler":
            # scheduler_args["algorithm_type"]=

        pipe.load_lora_weights(lora_path, weight_name=lora)
        # if lora2: pipe.load_lora_weights(lora2, weight_name=weight_name)
        # load lora into u-net only : pipeline.unet.load_attn_procs("jbilcke-hf/sdxl-cinematic-1", weight_name="pytorch_lora_weights.safetensors")

        pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config, **scheduler_args)
        # if text_inversion: pipe.load_textual_inversion(text_inversion)

        print(f"{tc()} set offload {cpu_offload} and sequential as {sequential_offload} for {device} device") #debug 
        if device=="cuda":
            if sequential_offload: pipe.enable_sequential_cpu_offload()
            if cpu_offload: pipe.enable_model_cpu_offload() 

        gen_args = {}
        if dynamic_guidance:
            print(f"{tc()} set dynamic cfg") #debug
            def dynamic_cfg(pipe, step_index, timestep, callback_key):
                if step_index == int(pipe.num_timesteps * 0.5):
                    callback_key['prompt_embeds'] = callback_key['prompt_embeds'].chunk(2)[-1]
                    callback_key['add_text_embeds'] = callback_key['add_text_embeds'].chunk(2)[-1]
                    callback_key['add_time_ids'] = callback_key['add_time_ids'].chunk(2)[-1]
                    pipe._guidance_scale = 0.0
                return callback_key
            
            gen_args["callback_on_step_end"]=dynamic_cfg
            gen_args["callback_on_step_end_tensor_inputs"]=['prompt_embeds', 'add_text_embeds','add_time_ids']

        if scheduler == "AysSchedules":
            timesteps = AysSchedules[model_ays] # should be autodetected
            gen_args["timesteps"]=timesteps

        print(f"{tc()} set generator") #debug
        generator = torch.Generator(device=device)

        print(f"{tc()} begin queue loop...") #debug

        if compile_unet: pipe.unet = torch.compile(pipe.unet, mode="reduce-overhead", fullgraph=True)
        for i, generation in enumerate(queue, start=1):
            image_start = perf_counter()                        #start the metric stopwatch
            print(f"{tc()} planting seed {generation['seed']}...") #debug
            seed_planter(generation['seed'])
            generator.manual_seed(generation['seed'])
            print(f"{tc()} inference device: {device}....") #debug

            generation['latents'] = pipe(
                prompt_embeds=generation['embeddings'][0],
                negative_prompt_embeds =generation['embeddings'][1],
                pooled_prompt_embeds=generation['embeddings'][2],
                negative_pooled_prompt_embeds=generation['embeddings'][3],
                num_inference_steps=inference_steps,
                generator=generator,
                output_type='latent',
                **gen_args,
            ).images 

        print(f"{tc()} empty cache...") #debug
        if clear_cache:
            pipe.unload_lora_weights()
            del pipe.unet
            gc.collect()
            if device == "cuda": torch.cuda.empty_cache()
            if device == "mps": torch.mps.empty_cache()


        ### USER OPTIONS  : VAE/SAVE/PREVIEW
        vae_find = "flat"
        file_prefix = "Shadowbox-"
        compress_level = 4 # optional png compression

        ### AUTOCONFIG OPTIONS  : VAE
        # pipe.upcast_vae()
        vae_tile = True #[compatability] tile vae input to lower memory
        vae_slice = False #[compatability] serialize vae to lower memory
        vae_default = "madebyollin/sdxl-vae-fp16-fix.safetensors" #[compatability] this should be detected by model type
        vae_config_file ="ssdxlvae.json" #[compatability] this too

        ### VAE SYSTEM
        vae_path = config.get_path("models.vae")
        autoencoder = os.path.join(vae_path,next((w for w in os.listdir(path=vae_path) if "flat" in w), vae_default)) #autoencoder wants full path and filename

        vae_config_path = os.path.join(config.get_path("models"),"metadata")
        symlnk = os.path.join(vae_config_path,"config.json") #autoencoder also wants specific filenames
        if os.path.isfile(symlnk): os.remove(symlnk)
        os.symlink(os.path.join(vae_config_path,vae_config_file),symlnk) #note: no 'i' in 'symlnk'


        print(f"{tc()} decoding using {autoencoder}...") #debug
        vae = AutoencoderKL.from_single_file(autoencoder, torch_dtype=torch.float16, cache_dir="vae_").to("cuda")
        #vae = FromOriginalModelMixin.from_single_file(autoencoder, config=vae_config).to(device)
        pipe.vae=vae
        pipe.upcast_vae()

        with torch.no_grad():
            counter = [s.endswith('png') for s in os.listdir(config.get_path("output"))].count(True) # get existing images
            for i, generation in enumerate(queue, start=1):
                generation['total_time'] = perf_counter() - image_start
                generation['latents'] = generation['latents'].to(next(iter(pipe.vae.post_quant_conv.parameters())).dtype)

                image = pipe.vae.decode(
                    generation['latents'] / pipe.vae.config.scaling_factor,
                    return_dict=False,
                )[0]

                image = pipe.image_processor.postprocess(image, output_type='pil')[0]

                print(f"{tc()} saving") #debug     
                counter += 1
                filename = f"{file_prefix}-{counter}-batch-{i}.png"

                image.save(os.path.join(config.get_path("output"), filename)) # optimize=True,

        if clear_cache:
            del pipe.vae
            gc.collect()
            if device == "cuda": torch.cuda.empty_cache()
            if device == "mps": torch.mps.empty_cache()

        ### METRICS
        images_totals = ', '.join(map(lambda generation: str(round(generation['total_time'], 1)), queue))
        print('Image time:', images_totals, 'seconds')

        images_average = round(sum(generation['total_time'] for generation in queue) / len(queue), 1)
        print('Average image time:', images_average, 'seconds')

        if device == "cuda":
            if linux: torch.cuda.memory._dump_snapshot("mem")
            else: 
                max_memory = round(torch.cuda.max_memory_allocated(device='cuda') / 1000000000, 2)
                print('Max. memory used:', max_memory, 'GB')



go = Inference().test_process()

    #transfer this block to nodes ----------->
    # <------------ end of block for nodes

    #transfer this block to system config .json ----------->
    # if torch.cuda.is_available(): 
    #     device = "cuda" # https://pytorch.org/docs/stable/torch_cuda_memory.html
    # else:  # https://pytorch.org/docs/master/notes/mps.html
    #    device = "mps" if (torch.backends.mps.is_available() & torch.backends.mps.is_built()) else "cpu"
    # <------------ end of block for system config .json
    # filename = 
    #     if not os.path.isdir(each):
    #         #full_path=os.path.join(path,each)
