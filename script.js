document.getElementById('fileInput').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onloadend = function() {
            const preview = document.getElementById('preview');
            preview.src = reader.result;
            document.getElementById('border').style.display = 'block';
        };
        reader.readAsDataURL(file);
    }
});
