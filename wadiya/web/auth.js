(function(){'use strict';
var form=document.getElementById('form'),msg=document.getElementById('msg');
form.addEventListener('submit',function(e){e.preventDefault();msg.textContent='';
var register=location.pathname==='/register';
var body={email:document.getElementById('email').value,password:document.getElementById('password').value};
if(register) body.display_name=document.getElementById('name').value;
fetch('/api/auth/'+(register?'register':'login'),{method:'POST',credentials:'same-origin',
headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
.then(function(r){return r.json().then(function(b){return {ok:r.ok,b:b}})})
.then(function(x){if(x.ok) location.href='/profile';else msg.textContent=(x.b.error&&x.b.error.message)||'Authentication failed.'})
.catch(function(){msg.textContent='Could not connect.'});
});})();