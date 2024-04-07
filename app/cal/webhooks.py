import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from firebase_functions.firestore_fn import (
    Change,
    DocumentSnapshot,
    Event,
    on_document_written,
)
from googleapiclient.errors import HttpError

from app.auth.views import get_token
from app.cal._utils import app_logger
from app.cal.tasks import (
    create_or_update_event_from_trip,
    create_or_update_trip_from_event,
    delete_calendar_watch_channel,
)
from app.models import DeleteWebhookChannel

cal_webhook_router = APIRouter()


@cal_webhook_router.post('/cal_webhook')
async def receive_webhook(request: Request, calendar_id: str):
    app_logger.info('Received webhook with calendar_id: %s', calendar_id)

    headers = request.headers
    app_logger.info(f'Received headers: {headers}')

    # Extract the data from the headers
    channel_id = headers.get('X-Goog-Channel-ID')
    channel_token = headers.get('X-Goog-Channel-Token')
    channel_expiration = headers.get('X-Goog-Channel-Expiration')
    resource_id = headers.get('X-Goog-Resource-ID')
    resource_uri = headers.get('X-Goog-Resource-URI')
    resource_state = headers.get('X-Goog-Resource-State')
    message_number = headers.get('X-Goog-Message-Number')

    # Log the extracted data
    app_logger.info(f'Channel ID: {channel_id}')
    app_logger.info(f'Channel Token: {channel_token}')
    app_logger.info(f'Channel Expiration: {channel_expiration}')
    app_logger.info(f'Resource ID: {resource_id}')
    app_logger.info(f'Resource URI: {resource_uri}')
    app_logger.info(f'Resource State: {resource_state}')
    app_logger.info(f'Message Number: {message_number}')

    if resource_uri:
        try:
            response = requests.get(resource_uri)
            app_logger.info('requesting resource_uri: %s', resource_uri)
            data = response.json()
        except Exception as e:
            app_logger.error(f'Error fetching resource: {e}')
            raise HTTPException(status_code=400, detail='Error fetching resource')

        try:
            event = Event(**data)
        except Exception as e:
            app_logger.error(f'Error creating Event: {e}')
            raise HTTPException(status_code=400, detail='Invalid event data')

        try:
            if calendar_id and event.id:
                app_logger.info('Creating or updating trip from event')
                create_or_update_trip_from_event(calendar_id, event)
            app_logger.info('Received event webhook')
        except Exception as e:
            app_logger.error(f'Error in create_or_update_trip_from_event: {e}')
            raise HTTPException(status_code=500, detail='Error processing event')


@cal_webhook_router.post('/delete_webhook_channel')
def delete_webhook_channel(data: DeleteWebhookChannel, token: str = Depends(get_token)):
    app_logger.info('Deleting webhook channel...')
    try:
        app_logger.info('Deleting channel: %s', data.channel_id)
        # Delete the channel
        delete_calendar_watch_channel(data.channel_id, data.resource_id)
        app_logger.info('Webhook channel successfully deleted.')
        return {'message': 'Webhook channel successfully deleted'}
    except HttpError as e:
        app_logger.error(f'Error deleting webhook channel: {e}')
        raise HTTPException(status_code=400, detail=str(e))


@on_document_written(document='trips/{tripId}')
def firestore_trigger(event: Event[Change[DocumentSnapshot]]) -> None:
    # Fetch the specific trip document
    trip_data = event.data.after.to_dict()

    # Call the create_or_update_event_from_trip function
    try:
        create_or_update_event_from_trip(trip_data['propertyRef'], trip_data['reference'])
    except HttpError as e:
        app_logger.error(f'Error creating event from trip: {e}')
        raise HTTPException(status_code=400, detail=str(e))
