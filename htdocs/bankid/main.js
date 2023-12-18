// BankID auth endpoint
//const authEndpoint = 'https://oidc.sandbox.bankid.cz/auth'; //Sandbox
const authEndpoint = 'https://oidc.bankid.cz/auth'; //Production

// Set Userinfo / Profile URL
//const userInfoEndpoint = 'https://oidc.sandbox.bankid.cz/profile'; //Sandbox
const userInfoEndpoint = 'https://oidc.bankid.cz/profile'; //Production

// Configuration of scopes from BankID dev portal
const scopes = ['openid', 'profile.name', 'profile.titles', 'profile.gender', 'profile.birthdate', 'profile.addresses', 'profile.email', 'profile.phonenumber', 'profile.email'];

// Query parameters for the auth call
const authUriParams = {
  client_id: '... .... ... ...', // Insert your client ID that you get after registration at www.bankid.cz
  state: 'Optional state value you want to pass on',
  scope: scopes.join(' '),
  // Redirect URI to your application - set your libary url and path to userinfo.html file
  //         you can add more redirect_uri values by repeating the line, if you like for some reason
  redirect_uri: 'https://opac.library.any/bankid/userinfo.html',
  //redirect_uri: 'https://opac.library.any/F/?func=file&file_name=bankid-userinfo',
  // reponse_type 'token' for implicit flow
  response_type: 'token',
};

// Query parameters in URL query string format
const uriParams = new URLSearchParams(authUriParams);

// Complete auth URI
const authUri = `${authEndpoint}?${uriParams}`;

// Get the login button
const loginButton = document.querySelector('#login') || document.createElement('span');
//const loginButton1 = document.querySelector('#login1');

// Change login button href to authUri
loginButton.href = authUri;
//loginButton1.href = authUri;

/* CALLING USERINFO/PROFILE EXAMPLE */

// Get the code block in html
const codeBlock = document.querySelector('code');

// Obtain access_token from URL fragment
const hash = window.location.hash.substring(1);
const params = new URLSearchParams(hash);
const accessToken = params.get('access_token');

const fetchUserinfo = async () => {
  // Pass access token to authorization header
  const headers = {
    Authorization: 'Bearer ' + accessToken,
  };

  try {
    const res = await fetch(userInfoEndpoint, { headers });
    // Retrieved userinfo / profile data in object format
    const json = await res.json();

    // Fill code block in HTML with data in JSON format for preview purposes
    codeBlock.innerHTML = JSON.stringify(json, null, 2);
  } catch (ex) {
    // handle errors
    console.error(ex);
  }
};

// Call userinfo if we received fragment data (we logged in)

if (hash) {
  fetchUserinfo();
}
