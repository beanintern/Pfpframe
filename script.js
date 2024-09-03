document.addEventListener('DOMContentLoaded', function() {
    const dropArea = document.getElementById('drop-area');
    const fileInput = document.getElementById('fileInput');
    const preview = document.getElementById('preview');
    const border = document.getElementById('border');
    const canvas = document.getElementById('canvas');
    const combinedImage = document.getElementById('combined');
    const ctx = canvas.getContext('2d');

    // Prevent default drag behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    // Highlight drop area when item is dragged over it
    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.classList.add('highlight');
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.classList.remove('highlight');
    });

    // Handle dropped files
    dropArea.addEventListener('drop', handleDrop, false);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const file = dt.files[0];
        handleFile(file);
    }

    // Handle selected files
    fileInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        handleFile(file);
    });

    function handleFile(file) {
        if (file) {
            const reader = new FileReader();
            reader.onloadend = function() {
                const img = new Image();
                img.onload = function() {
                    // Set canvas size to match the image size
                    canvas.width = img.width;
                    canvas.height = img.height;

                    // Draw the uploaded image onto the canvas
                    ctx.drawImage(img, 0, 0);

                    // Load and draw the border image on top of the uploaded image
                    const borderImg = new Image();
                    borderImg.crossOrigin = "anonymous"; // Enable CORS request
                    borderImg.src = border.src;
                    borderImg.onload = function() {
                        ctx.drawImage(borderImg, 0, 0, canvas.width, canvas.height);

                        // Convert the canvas to an image and display it
                        combinedImage.src = canvas.toDataURL('image/png');
                        combinedImage.style.display = 'block';

                        // Optionally hide the individual images
                        preview.style.display = 'none';
                        border.style.display = 'none';
                    };
                };
                img.src = reader.result;
            };
            reader.readAsDataURL(file);
        }
    }
});