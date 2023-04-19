import json
import sorl
from PIL import Image
from django.core.management.base import BaseCommand, CommandError
from moderation_queue.models import QueuedImage
from django.core.files.storage import default_storage


class Command(BaseCommand):
    def handle(self, **options):
        any_failed = False

        qs = QueuedImage.objects.filter(decision="undecided").exclude(
            detection_metadata=""
        )

        for qi in qs:
            queued_image = default_storage.open(qi.image.name, "r")
            try:
                detected = json.loads(qi.detection_metadata)
                if len(detected["FaceDetails"]) > 0:
                    self.rotate_queued_images(
                        s3_queued_image=queued_image,
                        queued_image=qi.image,
                        detected=detected,
                    )
                    sorl.thumbnail.delete(queued_image.name, delete_file=False)
                else:
                    msg = "No face details found for image: {queued_image.id}"
                    self.stdout.write(msg)
            except Exception as e:
                msg = "Skipping QueuedImage {id}: {error}"
                self.stdout.write(msg.format(id=qi.id, error=e))
                any_failed = True
            qi.save()
        if any_failed:
            raise CommandError("Broken images found (see above)")

    def rotate_queued_images(self, s3_queued_image, queued_image, detected):
        """
        Detects the rotation of an image and returns an integer
        """

        PILimage = Image.open(queued_image, formats=None)
        # Calculate the angle image is rotated by rounding the roll
        # value to the nearest multiple of 90
        roll = detected["FaceDetails"][0]["Pose"]["Roll"]
        img_rotation_angle = round(roll / 90) * 90
        rotated = PILimage.rotate(angle=img_rotation_angle, expand=True)
        s3_queued_image.write(queued_image.name)
        return rotated
