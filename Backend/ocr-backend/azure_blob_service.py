from azure.storage.blob import BlobServiceClient, ContentSettings
import uuid
import os


class BlobStorageService:

    def __init__(self, connection_string, container_name):
        self.container_name = container_name
        self.blob_service_client = BlobServiceClient.from_connection_string(
            connection_string
        )

    def upload_file(self, file_path, content_type="image/jpeg"):

        container_client = self.blob_service_client.get_container_client(
            self.container_name
        )

        file_extension = os.path.splitext(file_path)[1]
        file_name = f"{uuid.uuid4()}{file_extension}"

        blob_client = container_client.get_blob_client(file_name)

        with open(file_path, "rb") as data:
            blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type)
            )

        return blob_client.url