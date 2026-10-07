(function(){'use strict';
var box=document.getElementById('profile'),form=document.getElementById('form'),
name=document.getElementById('name'),msg=document.getElementById('msg');
fetch('/api/auth/me',{credentials:'same-origin'})
.then(function(r){if(r.status===401){location.href='/login';return null}return r.json()})
.then(function(x){if(!x)return;name.value=x.user.display_name;form.hidden=false;box.textContent=x.user.email})
.catch(function(){box.textContent='Could not load profile.'});
form.addEventListener('submit',function(e){e.preventDefault();msg.textContent='';
fetch('/api/auth/profile',{method:'PATCH',credentials:'same-origin',
headers:{'Content-Type':'application/json'},body:JSON.stringify({display_name:name.value})})
.then(function(r){return r.json().then(function(b){return {ok:r.ok,b:b}})})
.then(function(x){msg.textContent=x.ok?'Profile saved.':((x.b.error&&x.b.error.message)||'Update failed.')})
.catch(function(){msg.textContent='Could not connect.'});
});
document.getElementById('logout').addEventListener('click',function(){
fetch('/api/auth/logout',{method:'POST',credentials:'same-origin'}).then(function(){location.href='/login'});
});
})();