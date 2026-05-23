function startCountdown(deadline, elementId) {
    const target = new Date(deadline).getTime();
    const el = document.getElementById(elementId);

    const interval = setInterval(() => {
        const now = new Date().getTime();
        const distance = target - now;

        if (distance < 0) {
            clearInterval(interval);
            el.innerHTML = "<span class='text-danger'>Deadline Passed</span>";
            return;
        }

        const days = Math.floor(distance / (1000 * 60 * 60 * 24));
        const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));

        el.innerHTML = days + "d " + hours + "h left";
    }, 1000);
}
document.querySelectorAll(".progress-dynamic").forEach(el => {
    const value = el.dataset.progress;
    el.style.width = value + "%";
});