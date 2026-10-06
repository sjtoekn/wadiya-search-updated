document.addEventListener("DOMContentLoaded", function () {
  var form = document.getElementById("websiteSubmitForm");
  var input = document.getElementById("websiteUrl");
  var button = document.getElementById("websiteSubmitButton");
  var message = document.getElementById("websiteSubmitMessage");

  form.addEventListener("submit", async function (event) {
    event.preventDefault();

    var url = (input.value || "").trim();

    if (!url) {
      message.textContent = "Enter your website URL.";
      input.focus();
      return;
    }

    if (!/^https?:\/\//i.test(url)) {
      message.textContent = "Use a full URL starting with http:// or https://.";
      input.focus();
      return;
    }

    button.disabled = true;
    button.textContent = "Submitting…";
    message.textContent = "Submitting your website…";

    try {
      var response = await fetch("/api/submit", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({url: url})
      });

      var body = await response.json().catch(function () {
        return {};
      });

      if (!response.ok || !body.ok) {
        message.textContent =
          body && body.error && body.error.message
            ? body.error.message
            : "Could not submit this website right now.";
        return;
      }

      message.textContent = body.submitted
        ? "Website submitted successfully. Wadiya will discover and crawl it automatically."
        : "This website is already in the discovery queue.";
    } catch (error) {
      message.textContent = "Could not reach the website submission service.";
    } finally {
      button.disabled = false;
      button.textContent = "Submit website";
    }
  });
});
