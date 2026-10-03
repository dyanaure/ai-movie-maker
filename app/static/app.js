let characters=[
{name:"Elara",role:"Queen / protagonist",locked:false,image:null},
{name:"Varyx",role:"Dragon King",locked:false,image:null},
{name:"Cassian",role:"King / betrayer",locked:false,image:null},
{name:"Seraphine",role:"Lady / rival",locked:false,image:null}
];

function show(id){document.querySelectorAll('main section').forEach(x=>x.classList.add('hidden'));document.getElementById(id).classList.remove('hidden')}
function goCharacters(){if(!document.getElementById('script').value.trim()){alert('Paste your screenplay first.');return}renderCast();show('characters')}
function renderCast(){const root=document.getElementById('cast');root.innerHTML='';characters.forEach((c,i)=>{const d=document.createElement('div');d.className='card';d.innerHTML=`
<div class="portrait">${c.image?`<img src="${c.image}">`:'<span>Reference image</span>'}</div>
<input type="text" value="${c.name}" oninput="characters[${i}].name=this.value" placeholder="Character name">
<input type="text" value="${c.role}" oninput="characters[${i}].role=this.value" placeholder="Role / description">
<label class="upload">Upload reference image<input type="file" accept="image/*" onchange="pickImage(event,${i})"></label>
<button class="lock ${c.locked?'locked':''}" onclick="toggleLock(${i})">${c.locked?'🔒 Locked':'🔓 Lock Character'}</button>`;root.appendChild(d)})}
function pickImage(e,i){const f=e.target.files[0];if(!f)return;const r=new FileReader();r.onload=()=>{characters[i].image=r.result;characters[i].locked=false;renderCast()};r.readAsDataURL(f)}
function toggleLock(i){if(!characters[i].image){alert('Upload a reference image first.');return}characters[i].locked=!characters[i].locked;renderCast()}
function addCharacter(){characters.push({name:'New Character',role:'',locked:false,image:null});renderCast()}
async function saveProject(){const payload={title:document.getElementById('title').value,script:document.getElementById('script').value,aspect_ratio:document.getElementById('ratio').value,visual_style:document.getElementById('look').value,characters:characters.map(({name,role,locked})=>({name,role,locked}))};const res=await fetch('/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await res.json();document.getElementById('status').textContent=data.message||'Project saved.'}
renderCast();