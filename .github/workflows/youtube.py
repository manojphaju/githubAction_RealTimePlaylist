import logging
from pprint import pformat
import sys
from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.serialization import StringSerializer
from confluent_kafka.schema_registry.avro import AvroSerializer

import requests
import json 

baseURL = 'https://www.googleapis.com/youtube/v3/'

# page_token - getting the data per page
def fetch_playlist_items_page(google_api_key,youtube_playlist_id, page_token=None):
    response = requests.get(baseURL + "playlistItems", params={
    "key":google_api_key,
    "playlistId":youtube_playlist_id,
    "part":"contentDetails",
    "pageToken":page_token
    })

    payload=json.loads(response.text)
    logging.debug("GOT %s", payload)
    return payload

def fetch_videos_page(google_api_key,video_id, page_token=None):
    response = requests.get(baseURL + "videos", params={
    "key":google_api_key,
    "id":video_id,
    # "part":"contentDetails",
    "part":"snippet,statistics",
    "pageToken":page_token
    })

    payload=json.loads(response.text)
    logging.debug("GOT %s", payload)
    return payload


def fetch_playlist_items(google_api_key,youtube_playlist_id, page_token=None):
    #fetch one page
    payload = fetch_playlist_items_page(google_api_key,youtube_playlist_id,page_token)
    # Handling generator using yield function
    # yield function gives the every infomation available on each page
    yield from payload["items"]

    next_page_token=payload.get("nextPageToken")

    if next_page_token is not None:
        yield from fetch_playlist_items(google_api_key,youtube_playlist_id, next_page_token)



def fetch_videos(google_api_key,youtube_playlist_id, page_token=None):
    #fetch one page
    payload = fetch_videos_page(google_api_key,youtube_playlist_id,page_token)
    #Handling generator
    yield from payload["items"]
    # making nextPageToken optional for last page
    next_page_token=payload.get("nextPageToken")
    # recursive call function
    if next_page_token is not None:
        yield from fetch_videos(google_api_key,youtube_playlist_id, next_page_token)


def summarize_video(video):
    return {
        "video_id": video["id"],
        "title": video["snippet"]["title"],
        "views": int(video["statistics"].get("viewCount",0)),
        "likes": int(video["statistics"].get("likeCount",0)),
        "comments": int(video["statistics"].get("commentCount",0))
    }

def on_delivery(err, record):
    pass

def main():
    logging.info("START")

    # with open('config.json') as json_file:
    #     data=json.load(json_file)

    with open('.github/workflows/config.json') as json_file:
        data=json.load(json_file)

    google_api_key=data['google_api_key']
    youtube_playlist_id=data['youtube_playlist_id']


    schema_registry_client = SchemaRegistryClient(data["schema_registry"])
    youtube_videos_value_schema=schema_registry_client.get_latest_version("youtube_videos-value")

    kafka_config= data["kafka"] | {
        "key.serializer": StringSerializer(), 
        "value.serializer": AvroSerializer(schema_registry_client,youtube_videos_value_schema.schema.schema_str)
    }
    producer= SerializingProducer(kafka_config)

    for video_item in fetch_playlist_items(google_api_key, youtube_playlist_id):
        video_id=video_item["contentDetails"]["videoId"]
        for video in fetch_videos(google_api_key,video_id):
            logging.info("GOT %s", pformat(summarize_video(video)))
        
         #kafka
            producer.produce(
                topic="youtube_videos",
                key=video_id,
                value={
                    "TITLE": video["snippet"]["title"],
                    "VIEWS": int(video["statistics"].get("viewCount",0)),
                    "LIKES": int(video["statistics"].get("likeCount",0)),
                    "COMMENTS": int(video["statistics"].get("commentCount",0))
                },
                on_delivery=on_delivery,
            )

        
    producer.flush()

    


if __name__== "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
